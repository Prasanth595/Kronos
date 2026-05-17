# Kronos Flask API

Thu muc nay chi chay backend API cho ung dung Kronos. UI hien tai nam trong `../webui-next` va chay bang Next.js tren port `3000`.

## Vai tro

- `webui/app.py`: Flask API, load model, load data va chay du bao.
- `webui/run.py`: script khoi dong backend API.
- `webui/requirements.txt`: dependency Python cho backend.
- `webui/prediction_results/`: noi luu ket qua du bao da sinh.

## Chay backend

```bash
cd webui
python run.py
```

Hoac:

```bash
cd webui
python app.py
```

Backend mac dinh chay tai:

```text
http://localhost:7070
```

Trang `/` cua Flask tra ve JSON thong tin service. No khong con serve UI cu nua.

## Chay UI Next.js

```bash
cd webui-next
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Mo UI tai:

```text
http://localhost:3000
```

Next.js rewrite cac request `/api/*` sang Flask backend:

```text
http://127.0.0.1:7070/api/*
```

## API chinh

- `GET /api/health`: kiem tra backend co dang song khong.
- `GET /api/data-files`: lay danh sach file du lieu trong `data/`.
- `POST /api/load-data`: doc file du lieu va tra thong tin tong quan.
- `GET /api/available-models`: lay danh sach model Kronos ho tro.
- `GET /api/model-status`: xem model da load chua.
- `POST /api/load-model`: load model Kronos vao RAM/CPU/GPU.
- `POST /api/unload-model`: go model hien tai khoi RAM/VRAM de chuyen model khac.
- `POST /api/predict`: chay du bao va tra ket qua cho UI.

## Dinh dang du lieu

Cot bat buoc:

- `open`
- `high`
- `low`
- `close`

Cot tuy chon:

- `volume`
- `amount`
- `timestamps`, `timestamp` hoac `date`

## Luu y

- Flask `7070` la API service, khong phai giao dien nguoi dung.
- Next.js `3000` la giao dien chinh.
- Neu can deploy sau nay, nen deploy/tach lifecycle cua Python API va Next.js UI ro rang.
