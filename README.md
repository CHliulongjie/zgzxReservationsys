# 中国中学场馆预约系统

> **⚠️ 测试版本** - 此版本为测试版本，不代表最终结果。

## 项目简介

中国中学场馆预约系统，支持体育场馆、尔雅轩电影等预约功能。

## 当前版本修改内容

1. 集成了统一的权限系统
2. 支持通过识别码(UID)验证权限
3. 优化了预约流程

## 技术栈

- Python 3.x
- SQLite
- Windows GUI (Tkinter/PyQt)

## 项目结构

```
├── main.py             # 主程序入口
├── data/               # 数据文件
├── permissions/        # 权限数据库
│   └── reservation_permissions.db
└── README.md           # 项目说明
```

## 许可证

MIT License