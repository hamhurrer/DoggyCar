#include "face_timestamp.h"
#include "my_usart.h"
#include "my_usart1_user.h"
#include "esp_log.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "TIMESTAMP";

// ========================================
// 人脸检测记录
// ========================================
static face_timestamp_t face_records[MAX_TIMESTAMP_RECORDS];
static uint32_t face_record_count = 0;
static uint32_t face_write_index = 0;
static int64_t face_last_period_start = 0;
static bool face_detected_in_period = false;
static face_timestamp_t face_last_timestamp = {0, 0, DETECTION_HUMAN};
static bool face_has_record = false;

// ========================================
// 猫脸检测记录
// ========================================
static face_timestamp_t cat_records[MAX_CAT_TIMESTAMP_RECORDS];
static uint32_t cat_record_count = 0;
static uint32_t cat_write_index = 0;
static int64_t cat_last_period_start = 0;
static bool cat_detected_in_period = false;
static face_timestamp_t cat_last_timestamp = {0, 0, DETECTION_CAT};
static bool cat_has_record = false;

// ========================================
// 常量
// ========================================
static const int64_t PERIOD_US = 500000; // 半秒 = 500,000微秒

// ========================================
// 初始化
// ========================================
void face_timestamp_init(void)
{
    // 人脸记录初始化
    memset(face_records, 0, sizeof(face_records));
    face_record_count = 0;
    face_write_index = 0;
    face_last_period_start = 0;
    face_detected_in_period = false;
    face_has_record = false;

    // 猫脸记录初始化
    memset(cat_records, 0, sizeof(cat_records));
    cat_record_count = 0;
    cat_write_index = 0;
    cat_last_period_start = 0;
    cat_detected_in_period = false;
    cat_has_record = false;

    ESP_LOGI(TAG, "Timestamp module initialized (period: 500ms)");
    ESP_LOGI(TAG, "- Human records: %d max", MAX_TIMESTAMP_RECORDS);
    ESP_LOGI(TAG, "- Cat records: %d max", MAX_CAT_TIMESTAMP_RECORDS);
}

// ========================================
// 人脸时间戳记录
// ========================================
bool face_timestamp_record(bool face_detected)
{
    if (!face_detected)
    {
        return false;
    }

    int64_t current_time = esp_timer_get_time();
    int64_t current_period = current_time / PERIOD_US;
    int64_t last_period = face_last_period_start / PERIOD_US;

    // 检查是否进入新的周期
    if (current_period > last_period)
    {
        face_detected_in_period = false;
        face_last_period_start = current_period * PERIOD_US;
    }

    // 如果当前周期已经记录过,直接返回
    if (face_detected_in_period)
    {
        return false;
    }

    // 记录新的时间戳
    face_detected_in_period = true;
    face_has_record = true;

    // 转换为秒和微秒
    face_last_timestamp.seconds = current_time / 1000000;
    face_last_timestamp.microseconds = current_time % 1000000;
    face_last_timestamp.type = DETECTION_HUMAN;

    // 存入循环缓冲区
    face_records[face_write_index] = face_last_timestamp;
    face_write_index = (face_write_index + 1) % MAX_TIMESTAMP_RECORDS;

    if (face_record_count < MAX_TIMESTAMP_RECORDS)
    {
        face_record_count++;
    }

    // 通过串口发送
    char msg[150];
    sprintf(msg, "HUMAN_FACE,TIME:%lu.%06lu,COUNT:%lu\r\n",
            (unsigned long)face_last_timestamp.seconds,
            (unsigned long)face_last_timestamp.microseconds,
            (unsigned long)face_record_count);
    Uart_Send_Data((uint8_t *)msg, strlen(msg));
    Uart1_Send_Data((uint8_t *)msg, strlen(msg));

    ESP_LOGI(TAG, "Human face at: %lu.%06lu (total: %lu)",
             (unsigned long)face_last_timestamp.seconds,
             (unsigned long)face_last_timestamp.microseconds,
             (unsigned long)face_record_count);

    return true;
}

// ========================================
// 猫脸时间戳记录
// ========================================
bool cat_timestamp_record(bool cat_detected)
{
    if (!cat_detected)
    {
        return false;
    }

    int64_t current_time = esp_timer_get_time();
    int64_t current_period = current_time / PERIOD_US;
    int64_t last_period = cat_last_period_start / PERIOD_US;

    // 检查是否进入新的周期
    if (current_period > last_period)
    {
        cat_detected_in_period = false;
        cat_last_period_start = current_period * PERIOD_US;
    }

    // 如果当前周期已经记录过,直接返回
    if (cat_detected_in_period)
    {
        return false;
    }

    // 记录新的时间戳
    cat_detected_in_period = true;
    cat_has_record = true;

    // 转换为秒和微秒
    cat_last_timestamp.seconds = current_time / 1000000;
    cat_last_timestamp.microseconds = current_time % 1000000;
    cat_last_timestamp.type = DETECTION_CAT;

    // 存入循环缓冲区
    cat_records[cat_write_index] = cat_last_timestamp;
    cat_write_index = (cat_write_index + 1) % MAX_CAT_TIMESTAMP_RECORDS;

    if (cat_record_count < MAX_CAT_TIMESTAMP_RECORDS)
    {
        cat_record_count++;
    }

    // 通过串口发送
    char msg[150];
    sprintf(msg, "CAT_FACE,TIME:%lu.%06lu,COUNT:%lu\r\n",
            (unsigned long)cat_last_timestamp.seconds,
            (unsigned long)cat_last_timestamp.microseconds,
            (unsigned long)cat_record_count);
    Uart_Send_Data((uint8_t *)msg, strlen(msg));
    Uart1_Send_Data((uint8_t *)msg, strlen(msg));

    ESP_LOGI(TAG, "Cat face at: %lu.%06lu (total: %lu)",
             (unsigned long)cat_last_timestamp.seconds,
             (unsigned long)cat_last_timestamp.microseconds,
             (unsigned long)cat_record_count);

    return true;
}

// ========================================
// 获取最后一次记录
// ========================================
bool face_timestamp_get_last(face_timestamp_t *timestamp)
{
    if (!face_has_record || timestamp == NULL)
    {
        return false;
    }
    *timestamp = face_last_timestamp;
    return true;
}

bool cat_timestamp_get_last(face_timestamp_t *timestamp)
{
    if (!cat_has_record || timestamp == NULL)
    {
        return false;
    }
    *timestamp = cat_last_timestamp;
    return true;
}

// ========================================
// 获取记录数量
// ========================================
uint32_t face_timestamp_get_count(void)
{
    return face_record_count;
}

uint32_t cat_timestamp_get_count(void)
{
    return cat_record_count;
}

// ========================================
// 按索引获取记录
// ========================================
bool face_timestamp_get_by_index(uint32_t index, face_timestamp_t *timestamp)
{
    if (timestamp == NULL || index >= face_record_count)
    {
        return false;
    }

    uint32_t actual_index;
    if (face_record_count < MAX_TIMESTAMP_RECORDS)
    {
        if (index >= face_write_index)
        {
            return false;
        }
        actual_index = face_write_index - 1 - index;
    }
    else
    {
        actual_index = (face_write_index - 1 - index + MAX_TIMESTAMP_RECORDS) % MAX_TIMESTAMP_RECORDS;
    }

    *timestamp = face_records[actual_index];
    return true;
}

bool cat_timestamp_get_by_index(uint32_t index, face_timestamp_t *timestamp)
{
    if (timestamp == NULL || index >= cat_record_count)
    {
        return false;
    }

    uint32_t actual_index;
    if (cat_record_count < MAX_CAT_TIMESTAMP_RECORDS)
    {
        if (index >= cat_write_index)
        {
            return false;
        }
        actual_index = cat_write_index - 1 - index;
    }
    else
    {
        actual_index = (cat_write_index - 1 - index + MAX_CAT_TIMESTAMP_RECORDS) % MAX_CAT_TIMESTAMP_RECORDS;
    }

    *timestamp = cat_records[actual_index];
    return true;
}

// ========================================
// 发送最后一次记录
// ========================================
void face_timestamp_send_last(void)
{
    if (!face_has_record)
    {
        const char *msg = "NO_HUMAN_FACE_YET\r\n";
        Uart_Send_Data((uint8_t *)msg, strlen(msg));
        return;
    }

    char msg[100];
    sprintf(msg, "LAST_HUMAN:%lu.%06lu\r\n",
            (unsigned long)face_last_timestamp.seconds,
            (unsigned long)face_last_timestamp.microseconds);
    Uart_Send_Data((uint8_t *)msg, strlen(msg));
}

void cat_timestamp_send_last(void)
{
    if (!cat_has_record)
    {
        const char *msg = "NO_CAT_FACE_YET\r\n";
        Uart_Send_Data((uint8_t *)msg, strlen(msg));
        return;
    }

    char msg[100];
    sprintf(msg, "LAST_CAT:%lu.%06lu\r\n",
            (unsigned long)cat_last_timestamp.seconds,
            (unsigned long)cat_last_timestamp.microseconds);
    Uart_Send_Data((uint8_t *)msg, strlen(msg));
}

// ========================================
// 发送所有记录
// ========================================
void face_timestamp_send_all(void)
{
    if (face_record_count == 0)
    {
        const char *msg = "NO_HUMAN_RECORDS\r\n";
        Uart_Send_Data((uint8_t *)msg, strlen(msg));
        return;
    }

    char header[80];
    sprintf(header, "=== HUMAN FACE: %lu ===\r\n", (unsigned long)face_record_count);
    Uart_Send_Data((uint8_t *)header, strlen(header));

    for (uint32_t i = 0; i < face_record_count; i++)
    {
        face_timestamp_t ts;
        if (face_timestamp_get_by_index(i, &ts))
        {
            char msg[100];
            sprintf(msg, "[%lu] %lu.%06lu\r\n",
                    (unsigned long)i,
                    (unsigned long)ts.seconds,
                    (unsigned long)ts.microseconds);
            Uart_Send_Data((uint8_t *)msg, strlen(msg));
        }
    }

    const char *end_msg = "=== END HUMAN ===\r\n\r\n";
    Uart_Send_Data((uint8_t *)end_msg, strlen(end_msg));
}

void cat_timestamp_send_all(void)
{
    if (cat_record_count == 0)
    {
        const char *msg = "NO_CAT_RECORDS\r\n";
        Uart_Send_Data((uint8_t *)msg, strlen(msg));
        return;
    }

    char header[80];
    sprintf(header, "=== CAT FACE: %lu ===\r\n", (unsigned long)cat_record_count);
    Uart_Send_Data((uint8_t *)header, strlen(header));

    for (uint32_t i = 0; i < cat_record_count; i++)
    {
        face_timestamp_t ts;
        if (cat_timestamp_get_by_index(i, &ts))
        {
            char msg[100];
            sprintf(msg, "[%lu] %lu.%06lu\r\n",
                    (unsigned long)i,
                    (unsigned long)ts.seconds,
                    (unsigned long)ts.microseconds);
            Uart_Send_Data((uint8_t *)msg, strlen(msg));
        }
    }

    const char *end_msg = "=== END CAT ===\r\n\r\n";
    Uart_Send_Data((uint8_t *)end_msg, strlen(end_msg));
}

// ========================================
// 清空所有记录
// ========================================
void face_timestamp_clear(void)
{
    // 清空人脸记录
    memset(face_records, 0, sizeof(face_records));
    face_record_count = 0;
    face_write_index = 0;
    face_has_record = false;

    // 清空猫脸记录
    memset(cat_records, 0, sizeof(cat_records));
    cat_record_count = 0;
    cat_write_index = 0;
    cat_has_record = false;

    const char *msg = "ALL_TIMESTAMPS_CLEARED\r\n";
    Uart_Send_Data((uint8_t *)msg, strlen(msg));

    ESP_LOGI(TAG, "All timestamp records cleared");
}