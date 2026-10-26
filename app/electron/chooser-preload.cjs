// The chooser's page answers through here: chooser.done(value).
const { contextBridge, ipcRenderer } = require('electron');

const id = process.argv.find((a) => a.startsWith('--chooser='))?.slice('--chooser='.length);
contextBridge.exposeInMainWorld('chooser', { done: (value) => ipcRenderer.send(id, value) });
