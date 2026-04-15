import { BrowserRouter, Routes, Route, Navigate } from "react-router";
import { Sidebar } from "./components/layout/sidebar";
import { Header } from "./components/layout/header";
import { LoginPage } from "./pages/login";
import { DashboardPage } from "./pages/dashboard";
import { InventoryPage } from "./pages/inventory";
import { ProductFormPage } from "./pages/product-form";
import { ProductDetailPage } from "./pages/product-detail";
import { ChatPage } from "./pages/chat";
import { KnowledgeBasePage } from "./pages/knowledge-base";
import { SettingsPage } from "./pages/settings";
import { useState } from "react";

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [isAuthenticated] = useState(true);

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <AppLayout>
              <DashboardPage />
            </AppLayout>
          }
        />
        <Route
          path="/inventory"
          element={
            <AppLayout>
              <InventoryPage />
            </AppLayout>
          }
        />
        <Route
          path="/inventory/new"
          element={
            <AppLayout>
              <ProductFormPage />
            </AppLayout>
          }
        />
        <Route
          path="/inventory/:id"
          element={
            <AppLayout>
              <ProductDetailPage />
            </AppLayout>
          }
        />
        <Route
          path="/inventory/:id/edit"
          element={
            <AppLayout>
              <ProductFormPage />
            </AppLayout>
          }
        />
        <Route
          path="/chat"
          element={
            <AppLayout>
              <ChatPage />
            </AppLayout>
          }
        />
        <Route
          path="/knowledge-base"
          element={
            <AppLayout>
              <KnowledgeBasePage />
            </AppLayout>
          }
        />
        <Route
          path="/settings"
          element={
            <AppLayout>
              <SettingsPage />
            </AppLayout>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}