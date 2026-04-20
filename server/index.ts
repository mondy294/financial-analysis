import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import app from "./app.js";
import { startFinancialMcpServer } from "./mcp/index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, "../dist");
const distIndexFile = path.join(distDir, "index.html");
const port = Number(process.env.PORT || 7070);

if (fs.existsSync(distDir)) {
  app.use(express.static(distDir));
}

app.get("*", (_request, response) => {
  if (fs.existsSync(distIndexFile)) {
    response.sendFile(distIndexFile);
    return;
  }

  response.status(200).send("Financial API server is running. Frontend dev server: http://localhost:4177");
});

app.listen(port, () => {
  console.log(`Financial API server is running at http://localhost:${port}`);
});

startFinancialMcpServer();
