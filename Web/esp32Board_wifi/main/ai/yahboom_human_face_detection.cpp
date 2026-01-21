#include "yahboom_human_face_detection.hpp"

#include "esp_log.h"
#include "esp_camera.h"
#include "my_usart.h"
#include "dl_image.hpp"
#include "human_face_detect_msr01.hpp"
#include "human_face_detect_mnp01.hpp"

#include "yahboom_ai_utils.hpp"
#include "my_user_iic.h"
#include "my_usart1_user.h"

#define TWO_STAGE_ON 1 // 1:把眼睛、鼻子这些都打印出来

static const char *TAG = "human_face_detection";

static QueueHandle_t xQueueFrameI = NULL;
static QueueHandle_t xQueueEvent = NULL;
static QueueHandle_t xQueueFrameO = NULL;
static QueueHandle_t xQueueResult = NULL;

static bool gEvent = true;
static bool gReturnFB = true;

char nodatabuff[20] = {'\0'};

static void task_process_handler(void *arg)
{
    camera_fb_t *frame = NULL;
    HumanFaceDetectMSR01 detector(0.3F, 0.3F, 10, 0.3F);
#if TWO_STAGE_ON
    HumanFaceDetectMNP01 detector2(0.4F, 0.3F, 10);
#endif

    while (true)
    {
        if (gEvent)
        {
            bool is_detected = false;
            if (xQueueReceive(xQueueFrameI, &frame, portMAX_DELAY))
            {
#if TWO_STAGE_ON
                std::list<dl::detect::result_t> &detect_candidates = detector.infer((uint16_t *)frame->buf, {(int)frame->height, (int)frame->width, 3});
                std::list<dl::detect::result_t> &detect_results = detector2.infer((uint16_t *)frame->buf, {(int)frame->height, (int)frame->width, 3}, detect_candidates);
#else
                std::list<dl::detect::result_t> &detect_results = detector.infer((uint16_t *)frame->buf, {(int)frame->height, (int)frame->width, 3});
#endif

                if (detect_results.size() > 0)
                {
                    draw_detection_result((uint16_t *)frame->buf, frame->height, frame->width, detect_results);
                    print_detection_result(detect_results);
                    is_detected = true;
                }
                else
                {
                    // 识别不到人脸
                    sprintf(nodatabuff, "$000,000,320,240,#");
                    Uart_Send_Data((uint8_t *)nodatabuff, strlen((char *)nodatabuff));
                    // 串口1同步
                    Uart1_Send_Data((uint8_t *)nodatabuff, strlen((char *)nodatabuff));

                    // I2C同步
                    set_IIC_data(0, 0, 320, 240);
                }
            }

            if (xQueueFrameO)
            {
                xQueueSend(xQueueFrameO, &frame, portMAX_DELAY);
            }
            else if (gReturnFB)
            {
                esp_camera_fb_return(frame);
            }
            else
            {
                free(frame);
            }

            // ========================================
            // 🔧 修改位置: 第 84-91 行
            // 原代码：每帧都发送 is_detected (包括 false)
            // 修改后：只在检测到人脸时才发送消息
            // ========================================
            if (xQueueResult && is_detected) // ⭐ 添加 && is_detected 条件
            {
                int face_detected = 1; // 发送 1 表示检测到人脸
                xQueueSend(xQueueResult, &face_detected, portMAX_DELAY);
            }
            // 如果没检测到人脸 (is_detected == false)，不发送任何消息
        }
    }
}

static void task_event_handler(void *arg)
{
    while (true)
    {
        xQueueReceive(xQueueEvent, &(gEvent), portMAX_DELAY);
    }
}

void register_human_face_detection(const QueueHandle_t frame_i,
                                   const QueueHandle_t event,
                                   const QueueHandle_t result,
                                   const QueueHandle_t frame_o,
                                   const bool camera_fb_return)
{
    xQueueFrameI = frame_i;
    xQueueFrameO = frame_o;
    xQueueEvent = event;
    xQueueResult = result;
    gReturnFB = camera_fb_return;

    xTaskCreatePinnedToCore(task_process_handler, TAG, 4 * 1024, NULL, 5, NULL, 0);
    if (xQueueEvent)
        xTaskCreatePinnedToCore(task_event_handler, TAG, 4 * 1024, NULL, 5, NULL, 1);
}