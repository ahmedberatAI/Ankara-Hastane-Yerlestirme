import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./style.css";
import "leaflet/dist/leaflet.css";
import "./permanent-design.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
