const { app, BrowserWindow } = require("electron");
const path = require("path");

const DEV_URL = "http://localhost:5173";

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    title: "SQLGen",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  win.loadURL(DEV_URL);
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
