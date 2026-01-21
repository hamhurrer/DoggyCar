#ifndef FACE_TIMESTAMP_H
#define FACE_TIMESTAMP_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_timer.h"
#include "esp_camera.h"

#ifdef __cplusplus
extern "C"
{
#endif

    // 检测类型
    typedef enum
    {
        DETECTION_HUMAN = 0,
        DETECTION_CAT = 1
    } detection_type_t;

    // 时间戳结构体
    typedef struct
    {
        uint32_t seconds;      // 秒数
        uint32_t microseconds; // 微秒数
        detection_type_t type; // 检测类型
    } face_timestamp_t;

// 时间戳记录数组大小
#define MAX_TIMESTAMP_RECORDS 100
#define MAX_CAT_TIMESTAMP_RECORDS 100

    /**
     * @brief 初始化时间戳管理模块
     */
    void face_timestamp_init(void);

    /**
     * @brief 记录人脸检测时间戳 (半秒周期内只记录第一次)
     * @param face_detected 是否检测到人脸
     * @return true: 本次记录了新时间戳, false: 未记录
     */
    bool face_timestamp_record(bool face_detected);

    /**
     * @brief 记录猫脸检测时间戳 (半秒周期内只记录第一次)
     * @param cat_detected 是否检测到猫脸
     * @return true: 本次记录了新时间戳, false: 未记录
     */
    bool cat_timestamp_record(bool cat_detected);

    /**
     * @brief 获取最后一次检测到人脸的时间戳
     * @param timestamp 输出参数,存储时间戳
     * @return true: 获取成功, false: 还没有检测记录
     */
    bool face_timestamp_get_last(face_timestamp_t *timestamp);

    /**
     * @brief 获取最后一次检测到猫脸的时间戳
     * @param timestamp 输出参数,存储时间戳
     * @return true: 获取成功, false: 还没有检测记录
     */
    bool cat_timestamp_get_last(face_timestamp_t *timestamp);

    /**
     * @brief 获取所有记录的人脸时间戳数量
     * @return 时间戳记录数量
     */
    uint32_t face_timestamp_get_count(void);

    /**
     * @brief 获取所有记录的猫脸时间戳数量
     * @return 时间戳记录数量
     */
    uint32_t cat_timestamp_get_count(void);

    /**
     * @brief 获取指定索引的人脸时间戳
     * @param index 索引 (0为最新的记录)
     * @param timestamp 输出参数,存储时间戳
     * @return true: 获取成功, false: 索引超出范围
     */
    bool face_timestamp_get_by_index(uint32_t index, face_timestamp_t *timestamp);

    /**
     * @brief 获取指定索引的猫脸时间戳
     * @param index 索引 (0为最新的记录)
     * @param timestamp 输出参数,存储时间戳
     * @return true: 获取成功, false: 索引超出范围
     */
    bool cat_timestamp_get_by_index(uint32_t index, face_timestamp_t *timestamp);

    /**
     * @brief 通过串口发送最后一次人脸时间戳
     */
    void face_timestamp_send_last(void);

    /**
     * @brief 通过串口发送最后一次猫脸时间戳
     */
    void cat_timestamp_send_last(void);

    /**
     * @brief 通过串口发送所有人脸时间戳记录
     */
    void face_timestamp_send_all(void);

    /**
     * @brief 通过串口发送所有猫脸时间戳记录
     */
    void cat_timestamp_send_all(void);

    /**
     * @brief 清空所有时间戳记录
     */
    void face_timestamp_clear(void);

#ifdef __cplusplus
}
#endif

#endif // FACE_TIMESTAMP_H