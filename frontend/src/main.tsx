import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

const contenedor = document.getElementById("root");
if (!contenedor) throw new Error("No se encontró el nodo raíz");

createRoot(contenedor).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
