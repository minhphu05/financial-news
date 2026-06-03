import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

// Apply persisted theme class before first paint to prevent flash.
const storedTheme = localStorage.getItem("fn-theme");
const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
const theme = storedTheme === "light" || storedTheme === "dark" ? storedTheme : prefersDark ? "dark" : "light";
document.documentElement.classList.add(theme);

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing #root element");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
