import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import { Routes, Route } from "react-router-dom";
import { ThemeProvider } from "./context/ThemeContext";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/common/ProtectedRoute";
import Sidebar from "./components/layout/Sidebar";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import Home from "./pages/Home";
import Dashboard from "./pages/Dashboard";
import Graph from "./pages/Graph";
import Documents from "./pages/Documents";
import Tasks from "./pages/Tasks";
import Settings from "./pages/Settings";

// ── Toast Context ──────────────────────────────────────────────
type ToastType = "success" | "error" | "info";
interface ToastContextType {
  showToast: (message: string, type?: ToastType) => void;
}
const ToastContext = createContext<ToastContextType>({ showToast: () => {} });
export const useToast = () => useContext(ToastContext);

function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<{ id: number; message: string; type: ToastType }[]>([]);

  const showToast = useCallback((message: string, type: ToastType = "info") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3000);
  }, []);

  const toastColors: Record<ToastType, string> = {
    success: "#4caf82",
    error: "#e24b4a",
    info: "var(--accent)",
  };

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div style={{ position: "fixed", bottom: 24, right: 24, display: "flex", flexDirection: "column", gap: 8, zIndex: 9999 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{
            background: toastColors[t.type], color: "#fff",
            padding: "10px 16px", borderRadius: 8, fontSize: 13,
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          }}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// ── 메인 레이아웃 ──────────────────────────────────────────────
function MainLayout() {
  // activeRoomId를 Sidebar와 Home이 공유
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleRoomCreated = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  const handleNewChat = () => {
    setActiveRoomId(null);
  };

  return (
    <div className="flex" style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      <Sidebar
        activeRoomId={activeRoomId}
        onSelectRoom={setActiveRoomId}
        onNewChat={handleNewChat}
        refreshTrigger={refreshTrigger}
      />
      <main className="flex-1 h-screen overflow-hidden" style={{ color: "var(--text-primary)" }}>
        <Routes>
          <Route path="/" element={
            <Home
              activeRoomId={activeRoomId}
              setActiveRoomId={setActiveRoomId}
              onRoomCreated={handleRoomCreated}
            />
          } />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/graph" element={<Graph onGoToAnalysis={() => {}} />} />
          <Route path="/documents" element={
            <Documents
              selectedDocId={null}
              docViewMode="list"
              onNameClick={() => {}}
              onAnalysisClick={() => {}}
              onBack={() => {}}
            />
          } />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
        </main>
    </div>
  );
}

// ── 앱 루트 ────────────────────────────────────────────────────
function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <MainLayout />
                </ProtectedRoute>
              }
            />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;