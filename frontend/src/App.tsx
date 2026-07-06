import { Navigate, Route, Routes } from "react-router-dom";
import MainPage from "@/pages/MainPage";
import DeliveryProgressPage from "@/pages/DeliveryProgressPage";
import DeliveryResultPage from "@/pages/DeliveryResultPage";

export default function App() {
  return (
    <div className="min-h-full">
      <header className="border-b bg-white">
        <div className="mx-auto max-w-3xl px-6 py-4">
          <h1 className="text-lg font-semibold">PinkyCare</h1>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">
        <Routes>
          <Route path="/" element={<MainPage />} />
          <Route path="/delivery/:id" element={<DeliveryProgressPage />} />
          <Route path="/delivery/:id/result" element={<DeliveryResultPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
