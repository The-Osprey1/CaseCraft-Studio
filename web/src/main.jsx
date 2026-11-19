import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import "./index.css";

// Async failures outside React's render path: log them instead of failing silently.
window.addEventListener("unhandledrejection", (e) => {
  if (e.reason?.name === "AbortError") return;
  console.error("Unhandled promise rejection", e.reason);
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
