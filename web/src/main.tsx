import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
// react-image-crop's stylesheet, imported at the app entry (not in the
// component) so it stays out of the unit-test module graph.
import "react-image-crop/dist/ReactCrop.css";

const root = document.getElementById("root");
if (!root) throw new Error("elemento #root ausente no index.html");

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
