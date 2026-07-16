# 图搜流程提速说明

本项目的可恢复图搜脚本支持受控并发。默认 `--workers 1`，与原来的串行行为一致；
首次使用新并发参数时，先用 30 条样本验证 ERP 没有出现限流或错误率上升，再运行全量。

## URL 图搜（Seerfar / IXSPY）

```powershell
$env:PYTHONPATH="src"
& 'C:\Users\aibp\AppData\Local\Programs\Python\Python312\python.exe' -X utf8 scripts\incremental_erp_image_search.py `
  --source seerfar --product-type <品类> --base-dir . --limit 30 --workers 2 --delay 0.5
```

## 本地图片上传图搜（TikTok / FastMoss）

```powershell
$env:PYTHONPATH="src"
& 'C:\Users\aibp\AppData\Local\Programs\Python\Python312\python.exe' -X utf8 scripts\incremental_erp_image_search_local_files.py `
  --source seerfar --product-type <品类> --base-dir . --input-csv <带本地图路径的CSV> --limit 30 --workers 2 --delay 0.5
```

样本稳定后，去掉 `--limit 30` 即可跑全量。保持 `--workers 2`；只有连续全量稳定且没有 `429/502/503/504` 错误时，才考虑尝试 `--workers 3`。

脚本会保留已经写入结果 CSV 的 SKU。中断后使用相同命令重跑，会跳过已完成商品。

## DINOv2 精筛

```powershell
$env:PYTHONPATH="src"
& 'C:\Users\aibp\AppData\Local\Programs\Python\Python312\python.exe' -X utf8 scripts\chunked_rerank_image_search.py `
  --source seerfar --product-type <品类> --base-dir . --chunk-size 250 --checkpoint-every 4 --threshold 0.85
```

精筛现在默认每 4 个分块才重写一次完整候选 CSV，仍保留检查点恢复能力。DINOv2 当前运行在 CPU；批量推理和 GPU 迁移是下一阶段优化，不包含在本次改动中。
