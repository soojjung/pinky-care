# PinkyCare — Frontend

간호사가 사용하는 배송 관리 웹 UI. React + TypeScript + Vite + Tailwind CSS.

## 시작하기

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build
npm run preview
```

Node 버전은 `.nvmrc` (현재 20).

기본 API 서버 주소는 `http://localhost:8000`. 다른 주소로 붙이려면 `.env.local`에 `VITE_API_URL`을 지정하세요.

```env
# frontend/.env.local
VITE_API_URL=http://192.168.0.10:8000
```

## 폴더 구조

```
frontend/
├── src/
│   ├── components/               # 재사용 UI (Selector, Stepper)
│   ├── constants/                # 병실/물품 목록
│   ├── hooks/                    # useDeliveryStatus (SSE 구독)
│   ├── pages/                    # Main / Progress / Result
│   ├── services/                 # 외부 시스템과의 유일한 접점
│   ├── types/                    # Delivery 등 백엔드 계약 타입
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── vite.config.ts                # @/* → src/* alias
├── tsconfig.json
├── tailwind.config.js
└── package.json
```

## 서비스 계층 (Mock ↔ 실서버)

`src/services/index.ts`가 `DeliveryService`를 export 하고, 화면 코드는 이 인터페이스만 봅니다.

- **기본**: `apiDeliveryService` (FastAPI 백엔드 + SSE 구독)
- **오프라인 데모용**: `mockDeliveryService` (타이머 기반, 백엔드 불필요)

Mock으로 되돌리려면 `src/services/index.ts`의 import만 바꾸면 됩니다:

```ts
import { mockDeliveryService } from "./mockDeliveryService";
export const deliveryService: DeliveryService = mockDeliveryService;
```

## 화면 흐름

```
MainPage ──POST /deliveries──► DeliveryProgressPage ──terminal──► DeliveryResultPage
   (병실/물품)                    (SSE로 스텝 갱신)                 (성공/실패/재시도)
```

## 관련 문서

- API 명세서: [`../docs/api-spec.md`](../docs/api-spec.md)
- 시스템 아키텍처: [`../README.md`](../README.md)
- 백엔드: [`../backend/README.md`](../backend/README.md)
