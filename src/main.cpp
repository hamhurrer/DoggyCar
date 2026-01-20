#include <Arduino.h>
#include "SF_Servo.h"
#include "SF_IMU.h"
#include <math.h>
#include "bipedal_data.h"
#include "MPU6050_tockn.h"
#include "SF_CAN.h"
#include "config.h"
#include "SF_BLDC.h"
#include "pid.h"

// 电机实例化
SF_BLDC motors = SF_BLDC(Serial2);
SF_BLDC_DATA BLDCData;   
#define myID 0x01

// PID控制器（自稳+航点跟踪）
PIDController pitch_pid_mini = PIDController(0.2, 0.02, 0.001, 10000, 50);
PIDController roll_pid_mini = PIDController(0.1, 0.01, 0.001, 10000, 50);
//PIDController speed_pid = PIDController(1.0, 0.05, 0.01, 20, 50);  // 速度PID（ramp=20，limit=50）
PIDController yaw_pid = PIDController(2.0, 0.02, 0.05, 10, 30);    // 航向PID（ramp=10，limit=30）

// 矩形区域参数（单位：米）
#define RECT_LENGTH 3.5   // 长度（X轴）
#define RECT_WIDTH 8.4    // 宽度（Y轴）
#define WAYPOINT_INTERVAL 1  // 航点间隔
#define MAX_SPEED 50.0    // 最大速度
#define TARGET_DISTANCE 0.1   // 到达航点的判定距离（米）

// 航点结构体
typedef struct {
  float x;
  float y;
} Waypoint;

// 蛇形航点列表（预生成）
Waypoint waypoints[50];
int waypoint_count = 0;    // 实际航点数量
int current_waypoint = 0;  // 当前目标航点索引
bool mission_complete = false; // 任务完成标志

// 机器人当前位姿（简化：基于里程计估算，实际可结合IMU/编码器）
float robot_x = 0.0, robot_y = 0.0, robot_yaw = 0.0;

// CAN通信
SF_CAN CAN;
#define TRANSMIT_RATE_MS 1
unsigned long previousMillis = 0;

// 舵机相关
SF_Servo servos = SF_Servo(Wire);
IKparam IKParam;
float servo_off[8] = {6,-7,6,-3,7,-4,5,8};
float pitch_off=2, roll_off=-6;
int flat = 0;
motor_data MotorData;
motorstatus motorStatus;

// 步态相关
float t = 0;
const float pi = 3.1415926;
float height = 120;
float right_front = 70, right_rear = 70, left_front = 70, left_rear = 70;
float x1 = 0, x2 = 0, x3 = 0, x4 = 0, Y1 = right_front, y2 = left_front, y3 = right_rear, y4 = left_rear;
int r1 = -1, r2 = -1, r3 = 1, r4 = 1;
float faai = 0.5, Ts = 1;
float left_front_h = 60, left_rear_h = 60, right_front_h = 60, right_rear_h = 60;
float xf = 0, xs = 0, h = 60;
float sita1_1 = 0, sita1_2 = 0, sita1_3 = 0, sita1_4 = 0;
float sita2_1 = 0, sita2_2 = 0, sita2_3 = 0, sita2_4 = 0;
const float l1 = 60, l2 = 100;
int move_target = 0;
uint8_t motionMode = 1;  // 固定狗子步态
int controlmode = 1;     // 固定步态模式
int steadyState = 1;     // 开启自稳

// 逆解相关宏定义
#define L1 60
#define L2 100
#define L3 100
#define L4 60
#define L5 40
#define L6 0

// 限幅函数
#define _constrain(amt, low, high) ((amt) < (low) ? (low) : ((amt) > (high) ? (high) : (amt)))
float constrainValue(float value, float minValue, float maxValue) {
  return (value > maxValue) ? maxValue : (value < minValue) ? minValue : value;
}

// 生成蛇形航点
// 修改航点生成函数
void generate_waypoints() {
    waypoint_count = 0;
    bool reverse = false;
    float y_step = WAYPOINT_INTERVAL;  // 固定1m步长
    // 从y=0到y=8.4m逐行生成
    for (float y = 0; y <= RECT_WIDTH && waypoint_count < 49; y += y_step) {
        if (!reverse) {
            // 从左到右：x=0 → x=3.5
            waypoints[waypoint_count++] = {0.0, y};
            if (waypoint_count >= 50) break;
            waypoints[waypoint_count++] = {RECT_LENGTH, y};
        } else {
            // 从右到左：x=3.5 → x=0
            waypoints[waypoint_count++] = {RECT_LENGTH, y};
            if (waypoint_count >= 50) break;
            waypoints[waypoint_count++] = {0.0, y};
        }
        reverse = !reverse;
    }
    // 确保最后一个航点落在8.4m处（补足误差）
    if (waypoint_count > 0 && waypoints[waypoint_count-1].y < RECT_WIDTH) {
        waypoints[waypoint_count++] = reverse ? 
            Waypoint{0.0, RECT_WIDTH} : Waypoint{RECT_LENGTH, RECT_WIDTH};
    }
    Serial.print("实际生成航点数: ");
    Serial.println(waypoint_count);
}

// 里程计更新（简化：基于电机速度估算，实际需优化）
// 添加参数
#define WHEEL_RADIUS 0.03          // 轮子半径（米）
//#define MAX_SPEED_RPM 300.0        // 电机最大转速
//#define RPM_TO_MPS 0.005           // RPM转米/秒（需要校准）

void update_odometry() {
    static unsigned long last_odom_time = millis();
    unsigned long current_time = millis();
    float dt = (current_time - last_odom_time) / 1000.0;//相差的秒数
    Serial.print("时间差：");
    Serial.print(dt);
    if (dt <= 0 || dt > 0.1) {
        last_odom_time = current_time;  // 仅重置时间戳，不强制dt
        return;
    }
    last_odom_time = current_time;
    // 轮子实际线速度计算：RPM * 2πr / 60（r=0.03m）
    float wheel_circum = 2 * PI * WHEEL_RADIUS;  // 轮子周长
    float left_speed = motorStatus.M0Speed * wheel_circum ;  // RPM(转每秒)→m/s
    float right_speed = motorStatus.M1Speed * wheel_circum ;
    float linear_vel = (left_speed + right_speed) / 2.0;
    float angular_vel = (left_speed - right_speed) / 0.15;  // 轮距0.15m（需和实际匹配）rad/s
    // 更新位置（弧度计算，避免角度转换误差）
    robot_yaw += angular_vel * dt*180/ PI;//角度值
    float y_yaw=robot_yaw*PI/180;   //弧度值
    robot_x += linear_vel * cos(y_yaw) * dt;
    robot_y += linear_vel * sin(y_yaw) * dt;
    Serial.print("左轮速度：");
    Serial.print(left_speed);
    Serial.print("右轮速度：");
    Serial.print(right_speed);
    // 归一化航向角到-180~180°（更易计算误差）
    robot_yaw = fmod(robot_yaw + 180, 360) - 180;
    // 严格限制在长方形区域内
    robot_x = constrainValue(robot_x, 0, RECT_LENGTH);
    robot_y = constrainValue(robot_y, 0, RECT_WIDTH);
}
// 计算到目标航点的角度和距离
void calc_waypoint_target(float& target_yaw, float& target_dist) {
  if (current_waypoint >= waypoint_count) {
    mission_complete = true;
    target_yaw = 0;
    target_dist = 0;
    return;
  }
  
  Waypoint wp = waypoints[current_waypoint];
  float dx = wp.x - robot_x;
  float dy = wp.y - robot_y;
  
  // 计算距离
  target_dist = sqrt(dx*dx + dy*dy);
  
  // 计算目标航向（角度）
  target_yaw = atan2(dy, dx) * 180.0 / pi;
  if (target_yaw < 0) target_yaw += 360.0;
}

// 航点跟踪控制（输出电机目标速度）
void waypoint_control(float& motor1_target, float& motor2_target, 
                      float& send1_target, float& send2_target) {
    if (mission_complete) {
        motor1_target = motor2_target = send1_target = send2_target = 0;
        return;
    }
    
    // 计算当前航点
    Waypoint wp = waypoints[current_waypoint];
    float dx = wp.x - robot_x;
    float dy = wp.y - robot_y;
    float target_dist = sqrt(dx*dx + dy*dy);
    float target_yaw = atan2(dy, dx) * 180.0 / pi;
    
    // 归一化角度差
    float yaw_error = target_yaw - robot_yaw;
    while (yaw_error > 180) yaw_error -= 360;
    while (yaw_error < -180) yaw_error += 360;
    
    // 检查是否到达航点
    if (target_dist < TARGET_DISTANCE) {
        current_waypoint++;
        Serial.print("到达航点，下一个: ");
        Serial.println(current_waypoint);
        
        if (current_waypoint >= waypoint_count) {
            mission_complete = true;
            motor1_target = motor2_target = send1_target = send2_target = 0;
            Serial.println("所有航点完成！");
            return;
        }
        // 更新到下一个航点的参数
        wp = waypoints[current_waypoint];
        dx = wp.x - robot_x;
        dy = wp.y - robot_y;
        target_dist = sqrt(dx*dx + dy*dy);
        target_yaw = atan2(dy, dx) * 180.0 / pi;
        yaw_error = target_yaw - robot_yaw;
        while (yaw_error > 180) yaw_error -= 360;
        while (yaw_error < -180) yaw_error += 360;
    }
    
    // PID计算
    float steer = yaw_pid(yaw_error);  // 转向修正
    steer = constrainValue(steer, -15, 15);
     Serial.print("偏移量：");
    Serial.print(steer);
    // 根据距离调整速度：远距离快，近距离慢
    // float base_speed = min(MAX_SPEED, target_dist*1.0);
    // float min_speed = 5.0;  // 最小速度
    // float speed = max(min_speed, base_speed);
    float speed=1.0;//1秒5转
    float wheel_circum = 2 * PI * WHEEL_RADIUS;
    // 左转
    // 差速转向：左减右加（假设左轮为motor1，右轮为motor2）
    motor1_target = speed - steer*wheel_circum;  // 左后
    motor2_target = speed + steer*wheel_circum;  // 右后
    send1_target = speed + steer *wheel_circum;  // 右前
    send2_target = speed - steer *wheel_circum;  // 左前
    
    // 限幅
    motor1_target = motor1_target / wheel_circum;
    motor2_target = motor2_target / wheel_circum;
    send1_target = send1_target / wheel_circum;
    send2_target = send2_target / wheel_circum;
}

// 步态控制
void trot() {
  float sigma, zep, xep_b, xep_z, left_rear_zep, left_front_zep, right_rear_zep, right_front_zep;

  if (t <= Ts * faai) {
    sigma = 2 * pi * t / (faai * Ts);
    left_front_zep = left_front_h * (1 - cos(sigma)) / 2;
    left_rear_zep = left_rear_h * (1 - cos(sigma)) / 2;
    right_front_zep = right_front_h * (1 - cos(sigma)) / 2;
    right_rear_zep = right_rear_h * (1 - cos(sigma)) / 2;
    zep = h * (1 - cos(sigma)) / 2;
    xep_b = (xf - xs) * ((sigma - sin(sigma)) / (2 * pi)) + xs;
    xep_z = (xs - xf) * ((sigma - sin(sigma)) / (2 * pi)) + xf;

      //狗子步态
      //双足步态
      //固定值+遥控器前后和轮速反馈+遥控器左右+遥控器陀螺仪保持水平
      Y1 = left_front_h + 50 ;
      Y1 = constrainValue(Y1, 70, 150);
      y2 = right_front_h + 50 ;
      y2 = constrainValue(y2, 70, 150);
      y3 = right_rear_h + 50 ;
      y3 = constrainValue(y3, 70, 150);
      y4 = left_rear_h + 50 ;
      y4 = constrainValue(y4, 70, 150);

    x1 = -xep_z * r1 + move_target;
    x2 = -xep_b * r2 + move_target;
    x3 = -xep_z * r3 + move_target;
    x4 = -xep_b * r4 + move_target;
  } else if (t > Ts * faai && t <= Ts) {
    sigma = 2 * pi * (t - Ts * faai) / (faai * Ts);
    left_front_zep = left_front_h * (1 - cos(sigma)) / 2;
    left_rear_zep = left_rear_h * (1 - cos(sigma)) / 2;
    right_front_zep = right_front_h * (1 - cos(sigma)) / 2;
    right_rear_zep = right_rear_h * (1 - cos(sigma)) / 2;
    zep = h * (1 - cos(sigma)) / 2;
    xep_b = (xf - xs) * ((sigma - sin(sigma)) / (2 * pi)) + xs;
    xep_z = (xs - xf) * ((sigma - sin(sigma)) / (2 * pi)) + xf;

      Y1 = left_front_h + 50 ;
      Y1 = constrainValue(Y1, 70, 150);
      y2 = right_front_h + 50;
      y2 = constrainValue(y2, 70, 150);
      y3 = right_rear_h + 50;
      y3 = constrainValue(y3, 70, 150);
      y4 = left_rear_h + 50;
      y4 = constrainValue(y4, 70, 150);

    x1 = -xep_b * r1 + move_target;
    x2 = -xep_z * r2 + move_target;
    x3 = -xep_b * r3 + move_target;
    x4 = -xep_z * r4 + move_target;
  }
}

// 舵机角度设置
void setServoAngle(uint16_t servoLeftFront, uint16_t servoLeftRear,
                   uint16_t servoRightFront, uint16_t servoRightRear,
                   uint16_t servoBackLeftFront, uint16_t servoBackLeftRear,
                   uint16_t servoBackRightFront, uint16_t servoBackRightRear) {
  servos.setAngle(3, servoLeftFront + servo_off[2]);
  servos.setAngle(4, servoLeftRear + servo_off[3]);
  servos.setAngle(2, servoRightFront + servo_off[1]);
  servos.setAngle(1, servoRightRear + servo_off[0]);
  servos.setAngle(7, servoBackLeftFront + servo_off[6]);
  servos.setAngle(8, servoBackLeftRear + servo_off[7]);
  servos.setAngle(6, servoBackRightFront + servo_off[5]);
  servos.setAngle(5, servoBackRightRear + servo_off[4]);
}

// 逆运动学求解
void inverseKinematics() {
  float alpha1, alpha2, beta1, beta2;
  uint16_t servoLeftFront, servoLeftRear, servoRightFront, servoRightRear;
  uint16_t servoBackLeftFront, servoBackLeftRear, servoBackRightFront, servoBackRightRear;

  x3 = -x3;
  x4 = -x4;

  // 右前腿逆解
  float aRight = 2 * x2 * L1;
  float bRight = 2 * y2 * L1;
  float cRight = x2 * x2 + y2 * y2 + L1 * L1 - L2 * L2;
  float dRight = 2 * L4 * (x2 - L5);
  float eRight = 2 * L4 * y2;
  float fRight = ((x2 - L5) * (x2 - L5) + L4 * L4 + y2 * y2 - L3 * L3);

  IKParam.alphaRight = 2 * atan((bRight + sqrt((aRight * aRight) + (bRight * bRight) - (cRight * cRight))) / (aRight + cRight));
  IKParam.betaRight = 2 * atan((eRight - sqrt((dRight * dRight) + eRight * eRight - (fRight * fRight))) / (dRight + fRight));

  alpha1 = 2 * atan((bRight + sqrt((aRight * aRight) + (bRight * bRight) - (cRight * cRight))) / (aRight + cRight));
  alpha2 = 2 * atan((bRight - sqrt((aRight * aRight) + (bRight * bRight) - (cRight * cRight))) / (aRight + cRight));
  beta1 = 2 * atan((eRight + sqrt((dRight * dRight) + eRight * eRight - (fRight * fRight))) / (dRight + fRight));
  beta2 = 2 * atan((eRight - sqrt((dRight * dRight) + eRight * eRight - (fRight * fRight))) / (dRight + fRight));

  alpha1 = (alpha1 >= 0) ? alpha1 : (alpha1 + 2 * PI);
  alpha2 = (alpha2 >= 0) ? alpha2 : (alpha2 + 2 * PI);

  IKParam.alphaRight = (alpha1 >= PI / 4) ? alpha1 : alpha2;
  IKParam.betaRight = (beta1 >= 0 && beta1 <= PI / 4) ? beta1 : beta2;

  // 左前腿逆解
  float aLeft = 2 * x1 * L1;
  float bLeft = 2 * Y1 * L1;
  float cLeft = x1 * x1 + Y1 * Y1 + L1 * L1 - L2 * L2;
  float dLeft = 2 * L4 * (x1 - L5);
  float eLeft = 2 * L4 * Y1;
  float fLeft = ((x1 - L5) * (x1 - L5) + L4 * L4 + Y1 * Y1 - L3 * L3);

  alpha1 = 2 * atan((bLeft + sqrt((aLeft * aLeft) + (bLeft * bLeft) - (cLeft * cLeft))) / (aLeft + cLeft));
  alpha2 = 2 * atan((bLeft - sqrt((aLeft * aLeft) + (bLeft * bLeft) - (cLeft * cLeft))) / (aLeft + cLeft));
  beta1 = 2 * atan((eLeft + sqrt((dLeft * dLeft) + eLeft * eLeft - (fLeft * fLeft))) / (dLeft + fLeft));
  beta2 = 2 * atan((eLeft - sqrt((dLeft * dLeft) + eLeft * eLeft - (fLeft * fLeft))) / (dLeft + fLeft));

  alpha1 = (alpha1 >= 0) ? alpha1 : (alpha1 + 2 * PI);
  alpha2 = (alpha2 >= 0) ? alpha2 : (alpha2 + 2 * PI);

  IKParam.alphaLeft = (alpha1 >= PI / 4) ? alpha1 : alpha2;
  IKParam.betaLeft = (beta1 >= 0 && beta1 <= PI / 4) ? beta1 : beta2;

  // 角度转换
  int16_t alphaLeftToAngle = (int)((IKParam.alphaLeft / (2*PI)) * 360);
  int16_t betaLeftToAngle = (int)((IKParam.betaLeft / (2*PI)) * 360);
  int16_t alphaRightToAngle = (int)((IKParam.alphaRight / (2*PI)) * 360);
  int16_t betaRightToAngle = (int)((IKParam.betaRight / (2*PI)) * 360);

  servoLeftFront = 90 + betaLeftToAngle;
  servoLeftRear = 90 + alphaLeftToAngle;
  servoRightFront = 270 - betaRightToAngle;
  servoRightRear = 270 - alphaRightToAngle;

  // 右后腿逆解
  float aBackRight = 2 * x3 * L1;
  float bBackRight = 2 * y3 * L1;
  float cBackRight = x3 * x3 + y3 * y3 + L1 * L1 - L2 * L2;
  float dBackRight = 2 * L4 * (x3 - L5);
  float eBackRight = 2 * L4 * y3;
  float fBackRight = ((x3 - L5) * (x3 - L5) + L4 * L4 + y3 * y3 - L3 * L3);

  alpha1 = 2 * atan((bBackRight + sqrt((aBackRight * aBackRight) + (bBackRight * bBackRight) - (cBackRight * cBackRight))) / (aBackRight + cBackRight));
  alpha2 = 2 * atan((bBackRight - sqrt((aBackRight * aBackRight) + (bBackRight * bBackRight) - (cBackRight * cBackRight))) / (aBackRight + cBackRight));
  beta1 = 2 * atan((eBackRight + sqrt((dBackRight * dBackRight) + eBackRight * eBackRight - (fBackRight * fBackRight))) / (dBackRight + fBackRight));
  beta2 = 2 * atan((eBackRight - sqrt((dBackRight * dBackRight) + eBackRight * eBackRight - (fBackRight * fBackRight))) / (dBackRight + fBackRight));

  alpha1 = (alpha1 >= 0) ? alpha1 : (alpha1 + 2 * PI);
  alpha2 = (alpha2 >= 0) ? alpha2 : (alpha2 + 2 * PI);

  IKParam.alphaRight = (alpha1 >= PI / 4) ? alpha1 : alpha2;
  IKParam.betaRight = (beta1 >= 0 && beta1 <= PI / 4) ? beta1 : beta2;

  // 左后腿逆解
  float aBackLeft = 2 * x4 * L1;
  float bBackLeft = 2 * y4 * L1;
  float cBackLeft = x4 * x4 + y4 * y4 + L1 * L1 - L2 * L2;
  float dBackLeft = 2 * L4 * (x4 - L5);
  float eBackLeft = 2 * L4 * y4;
  float fBackLeft = ((x4 - L5) * (x4 - L5) + L4 * L4 + y4 * y4 - L3 * L3);

  alpha1 = 2 * atan((bBackLeft + sqrt((aBackLeft * aBackLeft) + (bBackLeft * bBackLeft) - (cBackLeft * cBackLeft))) / (aBackLeft + cBackLeft));
  alpha2 = 2 * atan((bBackLeft - sqrt((aBackLeft * aBackLeft) + (bBackLeft * bBackLeft) - (cBackLeft * cBackLeft))) / (aBackLeft + cBackLeft));
  beta1 = 2 * atan((eBackLeft + sqrt((dBackLeft * dBackLeft) + eBackLeft * eBackLeft - (fBackLeft * fBackLeft))) / (dBackLeft + fBackLeft));
  beta2 = 2 * atan((eBackLeft - sqrt((dBackLeft * dBackLeft) + eBackLeft * eBackLeft - (fBackLeft * fBackLeft))) / (dBackLeft + fBackLeft));

  alpha1 = (alpha1 >= 0) ? alpha1 : (alpha1 + 2 * PI);
  alpha2 = (alpha2 >= 0) ? alpha2 : (alpha2 + 2 * PI);

  IKParam.alphaLeft = (alpha1 >= PI / 4) ? alpha1 : alpha2;
  IKParam.betaLeft = (beta1 >= 0 && beta1 <= PI / 4) ? beta1 : beta2;

  // 角度转换
  int16_t alphaBackLefToAngle = (int)((IKParam.alphaLeft / (2*PI)) * 360);
  int16_t betaBackLeftToAngle = (int)((IKParam.betaLeft / (2*PI)) * 360);
  int16_t alphaBackRightToAngle = (int)((IKParam.alphaRight / (2*PI)) * 360);
  int16_t betaBackRightToAngle = (int)((IKParam.betaRight / (2*PI)) * 360);

  servoBackLeftFront = 90 + betaBackLeftToAngle;
  servoBackLeftRear = 90 + alphaBackLefToAngle;
  servoBackRightFront = 270 - betaBackRightToAngle;
  servoBackRightRear = 270 - alphaBackRightToAngle;

  // 驱动舵机
  setServoAngle(servoLeftFront, servoLeftRear, servoRightFront, servoRightRear,
                servoBackLeftFront, servoBackLeftRear, servoBackRightFront, servoBackRightRear);
}

// 获取电机数据
void getMotorValue() {
  BLDCData = motors.getBLDCData();
  motorStatus.M0Speed = motorStatus.M0SpdDir * BLDCData.M0_Vel;
  motorStatus.M1Speed = motorStatus.M1SpdDir * BLDCData.M1_Vel;
}

// 浮点转16位无符号整数
uint16_t float_to_uint(float x, float x_min, float x_max, uint8_t bits) {
  float span = x_max - x_min;
  float offset = x_min;
  return (uint16_t)((x - offset) * ((float)((1 << bits) - 1)) / span);
}

// CAN发送前驱速度指令
void can_control() {
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= TRANSMIT_RATE_MS) {
    previousMillis = currentMillis;
    getMotorValue();

    uint8_t motorcommand[8];
    MotorData.motor1taget = _constrain(MotorData.motor1taget, -100, 100);
    MotorData.motor2taget = _constrain(MotorData.motor2taget, -100, 100);
    uint16_t target1_int = float_to_uint(MotorData.motor1taget, -100.0, 100.0, 16);
    uint16_t target2_int = float_to_uint(MotorData.motor2taget, -100.0, 100.0, 16);

    uint32_t t_id = 0x02;
    motorcommand[0] = target1_int >> 8;
    motorcommand[1] = target1_int & 0xFF;
    motorcommand[2] = target2_int >> 8;
    motorcommand[3] = target2_int & 0xFF;
    motorcommand[4] = 0;
    motorcommand[5] = 0;
    motorcommand[6] = 0;
    motorcommand[7] = 0;

    CAN.sendMsg(&t_id, motorcommand);
  }
}

// 初始化机器人参数
void setRobotparam() {
  pitch_off = 2;
  roll_off = -1;
  //后面两个电机速度控制方向
  motorStatus.M0Dir = 1;
  motorStatus.M1Dir = 1;
  flat = 0;
  //后面两个电机速度反馈方向
  motorStatus.M0SpdDir = 1;
  motorStatus.M1SpdDir = -1;
  //前面两个电机速度控制方向
  motorStatus.M3Dir = 1;
  motorStatus.M4Dir = 1;
}

void setup() {
  Serial.begin(115200);
  setRobotparam();
  
  // 初始化I2C、CAN、舵机、电机
  Wire.begin(1, 2, 400000UL);
  CAN.init(CAN_TX, CAN_RX);
  CAN.setMode(1);
  CAN.setDeviceID(0x01);
  
  servos.init();
  servos.setAngleRange(0, 300);
  servos.setPluseRange(500, 2500);
  
  motors.init();
  motors.setModes(4, 4);

  // 初始化MPU6050
  MPU6050 mpu6050 = MPU6050(Wire);
  mpu6050.begin();
  mpu6050.calcGyroOffsets(true, 1000, 1000);

  // 生成蛇形航点
  generate_waypoints();
  Serial.print("生成航点数量：");
  Serial.println(waypoint_count);

  // 初始步态
  trot();
  inverseKinematics();
  delay(5000);
  Serial.println("初始化完成，开始蛇形运动");
}

void loop() {
  if (mission_complete) {
    // 任务完成，停止所有电机
    motors.setTargets(0, 0);
    MotorData.motor1taget = 0;
    MotorData.motor2taget = 0;
    servos.setAngle(1, 90);servos.setAngle(2, 90);
    servos.setAngle(3, 90);servos.setAngle(4, 90);
    servos.setAngle(5, 90);servos.setAngle(6, 90);
    servos.setAngle(7, 90);servos.setAngle(8, 90);
    can_control();
    Serial.println("任务完成，已停止");
    delay(1000);
    return;
  }

  // 更新里程计和IMU
  MPU6050 mpu6050 = MPU6050(Wire);
  mpu6050.update();
  robot_yaw = -mpu6050.getAngleZ();  // 从IMU获取航向
  update_odometry();

  // 航点跟踪控制
  float motor1target, motor2target, send1target, send2target;
  waypoint_control(motor1target, motor2target, send1target, send2target);
  
  // 设置电机速度
  motors.setTargets(motorStatus.M0Dir * motor1target, motorStatus.M1Dir * motor2target);
  MotorData.motor1taget = motorStatus.M4Dir * send1target;
  MotorData.motor2taget = motorStatus.M3Dir * send2target;

  // CAN通信
  can_control();

  // 自稳控制
  float pitch = mpu6050.getAngleX() + pitch_off;
  pitch = (pitch > -1 && pitch < 1) ? 0 : pitch;
  float roll = -mpu6050.getAngleY() + roll_off;
  roll = (roll > -0.1 && roll < 0.1) ? 0 : roll;
  
  float pout_roll = (0 - roll) * roll_pid_mini.P;
  static float iout_roll = 0;
  iout_roll += roll_pid_mini.I * (0 - roll);
  iout_roll = constrainValue(iout_roll, -70, 70);
  float target_roll = pout_roll + iout_roll;
  target_roll = constrainValue(target_roll, -90, 90);
  
  float pout_pitch = (0 - pitch) * pitch_pid_mini.P;
  static float iout_pitch = 0;
  iout_pitch += pitch_pid_mini.I * (0 - pitch);
  iout_pitch = constrainValue(iout_pitch, -70, 70);
  float target_pitch = pout_pitch + iout_pitch;
  target_pitch = constrainValue(target_pitch, -90, 90);

  // 步态更新
  t += 0.01;
  if (t >= Ts) t = 0;
  trot();
  inverseKinematics();

  // 打印状态（调试）
  static int count = 0;
  count++;
  if (count > 20) {
    count = 0;
    Serial.print("当前航点：");
    Serial.print(current_waypoint);
    Serial.print(" | 当前位置：(");
    Serial.print(robot_x, 2);
    Serial.print(",");
    Serial.print(robot_y, 2);
    Serial.print(") | 目标航点：(");
    Serial.print(waypoints[current_waypoint].x, 2);
    Serial.print(",");
    Serial.print(waypoints[current_waypoint].y, 2);
    Serial.println(")");
  }
}


 