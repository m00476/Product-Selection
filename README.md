# 跨境电商选品系统 — 数据底座

## 这是什么
读取 Seerfar/IXSPY/ERP 的 CSV 产物，归一化入 PostgreSQL。设计见
`docs/superpowers/specs/2026-06-04-product-sourcing-system-design.md`。

## 本地启动
```powershell
copy .env.example .env   # 按需修改
docker compose up -d postgres
pip install -e ".[dev]"
```

## 建表（迁移）
迁移在测试中自动执行；对本地库手动建表：
```powershell
python -c "from sourcing import config, db; c=db.connect(config.database_url()); db.run_migrations(c)"
```

## 导入数据
```powershell
python -m sourcing.cli --source seerfar --path <CSV路径> --product-type <品类>
```

## 测试
```powershell
pytest -v
```

## 数据来源
取数脚本在 `C:\Users\aibp\Desktop\518\apipy`（Selenium 探测+接口回放，产出 CSV 到 `input/<源>/<品类>/`）。本系统消费这些 CSV，不直接抓取。
