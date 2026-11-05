import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router";
import { App, HomePage, RequestList, SettingsPage, StatusPage } from "./pages";
import { Worksheet } from "./worksheet";
import { EvidenceReview } from "./review";
import { DecisionWorkbench } from "./decision";
import { ReceiptPage, SourceChanges } from "./receipt";
import { ThemeProvider } from "./ui";
import "./style.css";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 15000 },
    mutations: { retry: false },
  },
});
const router = createBrowserRouter([
  { path: "/", element: <HomePage /> },
  { path: "/status", element: <StatusPage /> },
  {
    element: <App />,
    children: [
      { path: "/sign-in", element: <Navigate to="/requests" replace /> },
      { path: "/requests", element: <RequestList /> },
      { path: "/requests/new", element: <Worksheet /> },
      { path: "/requests/:id", element: <Worksheet /> },
      { path: "/requests/:id/evidence", element: <EvidenceReview /> },
      { path: "/requests/:id/compare", element: <DecisionWorkbench /> },
      { path: "/requests/:id/changes/:attemptId", element: <SourceChanges /> },
      { path: "/releases/:receiptId", element: <ReceiptPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "*", element: <RequestList /> },
    ],
  },
]);
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider><RouterProvider router={router} /></ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
