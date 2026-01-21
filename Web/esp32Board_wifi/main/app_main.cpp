#include "yahboom_camera.h"
#include "app_mywifi.h"
#include "app_myhttpd.hpp"
#include "app_mymdns.h"

#include "esp_log.h"
#include "driver/spi_common.h"
#include "esp_chip_info.h"
#include "esp_system.h"
#include "esp_flash.h"

#include "my_usart.h"
#include "my_usart1_user.h"
#include "my_user_iic.h"
#include "mykey.h"
#include <cstring>

// AI检测需要的头文件
#include "dl_image.hpp"
#include "human_face_detect_msr01.hpp"
#include "human_face_detect_mnp01.hpp"
#include "cat_face_detect_mn03.hpp"
#include "yahboom_ai_utils.hpp"

// 时间戳模块 (支持人脸和猫脸)
#include "face_timestamp.h"

// ========================================
// 队列定义
// ========================================
static QueueHandle_t xQueueCameraFrame = NULL;  // 摄像头原始帧队列
static QueueHandle_t xQueueAIProcessed = NULL;  // AI处理后的帧队列
static QueueHandle_t xQueuemyvirtualKey = NULL; // 虚拟按键队列

static const char TAG[] = "main_AI_dual_detection";
char Version[] = "AI_V2.0_DUAL_TS";
uint16_t wifi_Mode = 2;

// ========================================
// 双AI检测任务 - 同时检测人脸和猫脸
// ========================================
static void dual_detection_task(void *arg)
{
    camera_fb_t *frame = NULL;

    ESP_LOGI(TAG, "Dual AI detection task started on core %d", xPortGetCoreID());

    // 创建检测器实例
    HumanFaceDetectMSR01 human_detector1(0.3F, 0.3F, 10, 0.3F);
    HumanFaceDetectMNP01 human_detector2(0.4F, 0.3F, 10);
    CatFaceDetectMN03 cat_detector(0.4F, 0.3F, 10, 0.3F);

    char nodatabuff[20] = {'\0'};

    while (1)
    {
        if (xQueueReceive(xQueueCameraFrame, &frame, portMAX_DELAY))
        {
            bool human_detected = false;
            bool cat_detected = false;

            // ========================================
            // 1. 人脸检测 (在画面上绘制红色框)
            // ========================================
            std::list<dl::detect::result_t> &human_candidates =
                human_detector1.infer((uint16_t *)frame->buf, {(int)frame->height, (int)frame->width, 3});
            std::list<dl::detect::result_t> &human_results =
                human_detector2.infer((uint16_t *)frame->buf, {(int)frame->height, (int)frame->width, 3}, human_candidates);

            if (human_results.size() > 0)
            {
                // 在画面上绘制人脸检测结果（红色框 + 关键点）
                draw_detection_result((uint16_t *)frame->buf, frame->height, frame->width, human_results);
                print_detection_result(human_results);
                human_detected = true;
            }
            else
            {
                // 未检测到人脸
                sprintf(nodatabuff, "$000,000,320,240,#");
                Uart_Send_Data((uint8_t *)nodatabuff, strlen(nodatabuff));
                Uart1_Send_Data((uint8_t *)nodatabuff, strlen(nodatabuff));
                set_IIC_data(0, 0, 320, 240);
            }

            // ========================================
            // 2. 猫脸检测 (绘制绿色框 + 输出日志)
            // ========================================
            std::list<dl::detect::result_t> &cat_results =
                cat_detector.infer((uint16_t *)frame->buf, {(int)frame->height, (int)frame->width, 3});

            if (cat_results.size() > 0)
            {
                cat_detected = true;

                ESP_LOGI(TAG, "🐱 Cat face detected! Count: %d", cat_results.size());

                // 遍历所有猫脸检测结果
                for (const auto &result : cat_results)
                {
                    // ✅ 在画面上绘制绿色边框（与人脸红色区分）
                    dl::image::draw_hollow_rectangle(
                        (uint16_t *)frame->buf,
                        frame->height,
                        frame->width,
                        result.box[0], result.box[1], // x, y
                        result.box[2], result.box[3], // w, h
                        0x07E0                        // 绿色 (RGB565: 0b00000_111111_00000)
                    );

                    // ✅ 串口输出猫脸位置
                    char catbuff[50];
                    sprintf(catbuff, "$CAT,%03d,%03d,%03d,%03d,#",
                            (int)result.box[0], (int)result.box[1],
                            (int)result.box[2], (int)result.box[3]);
                    Uart_Send_Data((uint8_t *)catbuff, strlen(catbuff));
                    Uart1_Send_Data((uint8_t *)catbuff, strlen(catbuff));

                    // ✅ ESP日志输出
                    ESP_LOGI(TAG, "Cat box: [%d,%d,%d,%d]",
                             (int)result.box[0], (int)result.box[1],
                             (int)result.box[2], (int)result.box[3]);
                }
            }

            // ========================================
            // 3. 记录时间戳 (人脸和猫脸分别记录)
            // ========================================
            if (human_detected)
            {
                face_timestamp_record(true);
            }

            if (cat_detected)
            {
                cat_timestamp_record(true);
            }

            // ========================================
            // 4. 发送处理后的帧到HTTP服务
            // ========================================
            xQueueSend(xQueueAIProcessed, &frame, portMAX_DELAY);
        }
    }

    vTaskDelete(NULL);
}

extern "C" void app_main(void)
{
    uint8_t ver_data[150] = "\0";

    // ========================================
    // 创建队列
    // ========================================
    xQueueCameraFrame = xQueueCreate(2, sizeof(camera_fb_t *));
    xQueueAIProcessed = xQueueCreate(2, sizeof(camera_fb_t *));
    xQueuemyvirtualKey = xQueueCreate(1, sizeof(int *));

    // ========================================
    // 初始化外设
    // ========================================
    My_Uart1_user_Init(xQueuemyvirtualKey);
    My_i2c_init(xQueuemyvirtualKey);
    app_mywifi_main();

    // ========================================
    // 摄像头初始化
    // ========================================
    my_register_camera(PIXFORMAT_RGB565, FRAMESIZE_QVGA, 2, xQueueCameraFrame);
    app_mymdns_main();

    // ========================================
    // 初始化时间戳模块
    // ========================================
    face_timestamp_init();

    // ========================================
    // 创建双AI检测任务 (核心0)
    // ========================================
    xTaskCreatePinnedToCore(
        dual_detection_task,
        "dual_ai_task",
        8 * 1024, // 8KB栈空间
        NULL,
        5, // 优先级5
        NULL,
        0 // 核心0
    );

    // ========================================
    // 注册HTTP服务
    // ========================================
    register_httpd(xQueueAIProcessed, NULL, true);

    // ========================================
    // 串口初始化
    // ========================================
    My_Uart_Init(xQueuemyvirtualKey);

    // ========================================
    // 发送版本信息
    // ========================================
    sprintf((char *)ver_data,
            "YAHBOOM Ver:%s\r\n"
            "[Human + Cat Face Detection]\r\n"
            "[Dual Timestamp System]\r\n",
            Version);
    Uart_Send_Data(ver_data, strlen((char *)ver_data));

    ESP_LOGI(TAG, "╔═══════════════════════════════════════════╗");
    ESP_LOGI(TAG, "║   Dual AI Detection System Ready!        ║");
    ESP_LOGI(TAG, "║   • Human Face: ✓ (RED box + keypoints)  ║");
    ESP_LOGI(TAG, "║   • Cat Face:   ✓ (GREEN box + log)      ║");
    ESP_LOGI(TAG, "║   • Period:     500ms                    ║");
    ESP_LOGI(TAG, "║   • Records:    100 each                 ║");
    ESP_LOGI(TAG, "╚═══════════════════════════════════════════╝");
}