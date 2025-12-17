# 日志模块
import logging
import os
from logging.handlers import RotatingFileHandler

# 初始化全局日志系统
def setup_logger(
    log_level=logging.INFO,
    log_dir="data/logs",
    log_file="system.log"
):
    
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    # 获取根日志记录器
    logger = logging.getLogger()
    logger.setLevel(log_level) # 设置日志器级别，低于此级别的日志会被过滤

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # 文件日志（支持日志轮转）
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3, # 保留3个备份文件
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # 添加 handler
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logging.info("日志系统初始化完成")

    return logger
