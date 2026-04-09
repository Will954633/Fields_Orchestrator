#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { google } from "googleapis";
import fs from "fs";
import path from "path";
import { Readable } from "stream";

// ── Credentials & Auth ──────────────────────────────────────────────

const oauthPath = process.env.GDRIVE_OAUTH_PATH;
const credentialsPath = process.env.GDRIVE_CREDENTIALS_PATH;

if (!oauthPath || !credentialsPath) {
  console.error("Missing GDRIVE_OAUTH_PATH or GDRIVE_CREDENTIALS_PATH");
  process.exit(1);
}

const oauthKeys = JSON.parse(fs.readFileSync(oauthPath, "utf-8"));
const credentials = JSON.parse(fs.readFileSync(credentialsPath, "utf-8"));

const { client_id, client_secret, redirect_uris } = oauthKeys.installed || oauthKeys.web;
const auth = new google.auth.OAuth2(client_id, client_secret, redirect_uris?.[0]);

auth.setCredentials({
  access_token: credentials.access_token,
  refresh_token: credentials.refresh_token,
  expiry_date: credentials.expiry_date,
});

// Persist refreshed tokens
auth.on("tokens", (tokens) => {
  try {
    const existing = JSON.parse(fs.readFileSync(credentialsPath, "utf-8"));
    const updated = { ...existing, ...tokens };
    fs.writeFileSync(credentialsPath, JSON.stringify(updated, null, 2));
  } catch (_) {
    // silent — don't crash the server over a token write failure
  }
});

const drive = google.drive({ version: "v3", auth });

// ── Helpers ──────────────────────────────────────────────────────────

const MAX_READ_BYTES = 512 * 1024; // 512KB cap for read_file

const EXPORT_MIME_MAP = {
  "application/vnd.google-apps.document": { mime: "text/markdown", ext: "md" },
  "application/vnd.google-apps.spreadsheet": { mime: "text/csv", ext: "csv" },
  "application/vnd.google-apps.presentation": { mime: "text/plain", ext: "txt" },
  "application/vnd.google-apps.drawing": { mime: "image/png", ext: "png" },
};

function isGoogleWorkspace(mimeType) {
  return mimeType?.startsWith("application/vnd.google-apps.");
}

function textResult(obj) {
  const text = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  return { content: [{ type: "text", text }] };
}

function errorResult(err) {
  const status = err?.response?.status || err?.code;
  let msg = err.message || String(err);
  if (status === 404) msg = `File not found: ${msg}`;
  else if (status === 403) msg = `Permission denied: ${msg}`;
  else if (status === 429) msg = `Rate limited — try again shortly.`;
  return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
}

async function wrap(fn) {
  try {
    return await fn();
  } catch (err) {
    return errorResult(err);
  }
}

const FILE_FIELDS = "id,name,mimeType,modifiedTime,createdTime,size,parents,webViewLink,shared,trashed";

// ── Tool Definitions ─────────────────────────────────────────────────

const TOOLS = [
  {
    name: "search",
    description:
      "Search for files in Google Drive. Supports natural language queries or raw Drive query syntax (e.g. name contains 'report' and mimeType='application/pdf').",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search query" },
        pageSize: { type: "number", description: "Max results (default 20, max 100)" },
      },
      required: ["query"],
    },
  },
  {
    name: "list_folder",
    description: "List contents of a Google Drive folder. Defaults to root if no folderId given.",
    inputSchema: {
      type: "object",
      properties: {
        folderId: { type: "string", description: "Folder ID (default: root)" },
        pageSize: { type: "number", description: "Max results (default 50, max 100)" },
        pageToken: { type: "string", description: "Pagination token from previous response" },
      },
    },
  },
  {
    name: "read_file",
    description:
      "Read the text content of a file. Google Docs export as Markdown, Sheets as CSV. Binary files return a message to use download_file instead. Capped at 512KB.",
    inputSchema: {
      type: "object",
      properties: {
        fileId: { type: "string", description: "The file ID" },
      },
      required: ["fileId"],
    },
  },
  {
    name: "read_file_metadata",
    description: "Get metadata for a file (name, type, size, parents, links, etc.).",
    inputSchema: {
      type: "object",
      properties: {
        fileId: { type: "string", description: "The file ID" },
      },
      required: ["fileId"],
    },
  },
  {
    name: "create_file",
    description:
      "Create a new file in Google Drive. For Google Docs, set mimeType to 'application/vnd.google-apps.document' and pass plain text content.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "File name" },
        content: { type: "string", description: "Text content (optional for folders)" },
        mimeType: {
          type: "string",
          description:
            "Target mimeType. Use 'application/vnd.google-apps.document' for Google Docs. Defaults to text/plain.",
        },
        folderId: { type: "string", description: "Parent folder ID (default: root)" },
      },
      required: ["name"],
    },
  },
  {
    name: "update_file",
    description: "Update the text content of an existing file. Works with Google Docs (provide plain text or markdown).",
    inputSchema: {
      type: "object",
      properties: {
        fileId: { type: "string", description: "The file ID" },
        content: { type: "string", description: "New text content" },
        mimeType: { type: "string", description: "Media mimeType for upload (default: text/plain)" },
      },
      required: ["fileId", "content"],
    },
  },
  {
    name: "create_folder",
    description: "Create a new folder in Google Drive.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Folder name" },
        parentId: { type: "string", description: "Parent folder ID (default: root)" },
      },
      required: ["name"],
    },
  },
  {
    name: "move_file",
    description: "Move a file to a different folder.",
    inputSchema: {
      type: "object",
      properties: {
        fileId: { type: "string", description: "The file ID to move" },
        newParentId: { type: "string", description: "Destination folder ID" },
      },
      required: ["fileId", "newParentId"],
    },
  },
  {
    name: "copy_file",
    description: "Copy a file. Optionally rename it or place it in a specific folder.",
    inputSchema: {
      type: "object",
      properties: {
        fileId: { type: "string", description: "Source file ID" },
        name: { type: "string", description: "Name for the copy (default: 'Copy of ...')" },
        folderId: { type: "string", description: "Destination folder ID" },
      },
      required: ["fileId"],
    },
  },
  {
    name: "delete_file",
    description: "Move a file to trash (not permanent deletion).",
    inputSchema: {
      type: "object",
      properties: {
        fileId: { type: "string", description: "The file ID to trash" },
      },
      required: ["fileId"],
    },
  },
  {
    name: "download_file",
    description: "Download a file from Google Drive to a local path. Exports Google Workspace files to appropriate formats.",
    inputSchema: {
      type: "object",
      properties: {
        fileId: { type: "string", description: "The file ID" },
        localPath: { type: "string", description: "Absolute local file path to save to" },
      },
      required: ["fileId", "localPath"],
    },
  },
  {
    name: "upload_file",
    description: "Upload a local file to Google Drive.",
    inputSchema: {
      type: "object",
      properties: {
        localPath: { type: "string", description: "Absolute local file path to upload" },
        name: { type: "string", description: "File name in Drive (default: local filename)" },
        folderId: { type: "string", description: "Destination folder ID (default: root)" },
        mimeType: { type: "string", description: "Override mimeType (auto-detected if omitted)" },
      },
      required: ["localPath"],
    },
  },
];

// ── Tool Handlers ────────────────────────────────────────────────────

async function handleSearch({ query, pageSize }) {
  // If query looks like raw Drive query syntax, use it directly
  const isRaw = /\b(name|mimeType|fullText|modifiedTime|parents)\b/.test(query);
  const q = isRaw ? query : `fullText contains '${query.replace(/'/g, "\\'")}'`;

  const res = await drive.files.list({
    q,
    pageSize: Math.min(pageSize || 20, 100),
    fields: `files(${FILE_FIELDS})`,
    orderBy: "modifiedTime desc",
  });
  return textResult({ count: res.data.files.length, files: res.data.files });
}

async function handleListFolder({ folderId, pageSize, pageToken }) {
  const parent = folderId || "root";
  const res = await drive.files.list({
    q: `'${parent}' in parents and trashed=false`,
    pageSize: Math.min(pageSize || 50, 100),
    pageToken: pageToken || undefined,
    fields: `nextPageToken,files(${FILE_FIELDS})`,
    orderBy: "folder,name",
  });
  return textResult({
    folderId: parent,
    count: res.data.files.length,
    nextPageToken: res.data.nextPageToken || null,
    files: res.data.files,
  });
}

async function handleReadFile({ fileId }) {
  // Get metadata first
  const meta = await drive.files.get({ fileId, fields: "id,name,mimeType,size" });
  const { mimeType, name, size } = meta.data;

  if (isGoogleWorkspace(mimeType)) {
    const exportInfo = EXPORT_MIME_MAP[mimeType];
    if (!exportInfo) {
      return textResult(`Cannot read Google Workspace type: ${mimeType}. Use download_file instead.`);
    }
    const res = await drive.files.export({ fileId, mimeType: exportInfo.mime }, { responseType: "text" });
    let text = typeof res.data === "string" ? res.data : JSON.stringify(res.data);
    if (text.length > MAX_READ_BYTES) {
      text = text.slice(0, MAX_READ_BYTES) + `\n\n--- TRUNCATED (${text.length} bytes total, cap ${MAX_READ_BYTES}) ---`;
    }
    return textResult({ name, mimeType, exportedAs: exportInfo.mime, content: text });
  }

  // Regular file
  if (parseInt(size) > MAX_READ_BYTES * 2) {
    return textResult(
      `File "${name}" is ${size} bytes — too large to read inline. Use download_file to save it locally.`
    );
  }

  try {
    const res = await drive.files.get({ fileId, alt: "media" }, { responseType: "text" });
    let text = typeof res.data === "string" ? res.data : JSON.stringify(res.data);
    if (text.length > MAX_READ_BYTES) {
      text = text.slice(0, MAX_READ_BYTES) + `\n\n--- TRUNCATED ---`;
    }
    return textResult({ name, mimeType, content: text });
  } catch (e) {
    if (e.message?.includes("not text")) {
      return textResult(`File "${name}" is binary (${mimeType}). Use download_file instead.`);
    }
    throw e;
  }
}

async function handleReadFileMetadata({ fileId }) {
  const res = await drive.files.get({ fileId, fields: FILE_FIELDS });
  return textResult(res.data);
}

async function handleCreateFile({ name, content, mimeType, folderId }) {
  const targetMime = mimeType || "text/plain";
  const requestBody = { name, parents: folderId ? [folderId] : undefined };

  let media;
  if (content) {
    // For Google Docs, upload as plain text and let Drive convert
    const uploadMime = isGoogleWorkspace(targetMime) ? "text/plain" : targetMime;
    requestBody.mimeType = targetMime;
    media = { mimeType: uploadMime, body: Readable.from([content]) };
  } else {
    requestBody.mimeType = targetMime;
  }

  const res = await drive.files.create({
    requestBody,
    media,
    fields: FILE_FIELDS,
  });
  return textResult({ created: true, file: res.data });
}

async function handleUpdateFile({ fileId, content, mimeType }) {
  // Check if target is a Google Doc — if so, upload as plain text
  const meta = await drive.files.get({ fileId, fields: "mimeType" });
  const uploadMime = isGoogleWorkspace(meta.data.mimeType) ? "text/plain" : (mimeType || "text/plain");

  const res = await drive.files.update({
    fileId,
    media: { mimeType: uploadMime, body: Readable.from([content]) },
    fields: FILE_FIELDS,
  });
  return textResult({ updated: true, file: res.data });
}

async function handleCreateFolder({ name, parentId }) {
  const res = await drive.files.create({
    requestBody: {
      name,
      mimeType: "application/vnd.google-apps.folder",
      parents: parentId ? [parentId] : undefined,
    },
    fields: FILE_FIELDS,
  });
  return textResult({ created: true, folder: res.data });
}

async function handleMoveFile({ fileId, newParentId }) {
  const meta = await drive.files.get({ fileId, fields: "parents" });
  const previousParents = (meta.data.parents || []).join(",");

  const res = await drive.files.update({
    fileId,
    addParents: newParentId,
    removeParents: previousParents,
    fields: FILE_FIELDS,
  });
  return textResult({ moved: true, file: res.data });
}

async function handleCopyFile({ fileId, name, folderId }) {
  const requestBody = {};
  if (name) requestBody.name = name;
  if (folderId) requestBody.parents = [folderId];

  const res = await drive.files.copy({ fileId, requestBody, fields: FILE_FIELDS });
  return textResult({ copied: true, file: res.data });
}

async function handleDeleteFile({ fileId }) {
  await drive.files.update({ fileId, requestBody: { trashed: true } });
  return textResult({ trashed: true, fileId });
}

async function handleDownloadFile({ fileId, localPath }) {
  const meta = await drive.files.get({ fileId, fields: "name,mimeType,size" });
  const { mimeType, name } = meta.data;

  // Ensure parent directory exists
  const dir = path.dirname(localPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  if (isGoogleWorkspace(mimeType)) {
    const exportInfo = EXPORT_MIME_MAP[mimeType];
    if (!exportInfo) {
      return textResult(`Cannot export Google Workspace type: ${mimeType}`);
    }
    const res = await drive.files.export({ fileId, mimeType: exportInfo.mime }, { responseType: "arraybuffer" });
    fs.writeFileSync(localPath, Buffer.from(res.data));
    return textResult({ downloaded: true, name, exportedAs: exportInfo.mime, localPath, bytes: res.data.byteLength });
  }

  const res = await drive.files.get({ fileId, alt: "media" }, { responseType: "arraybuffer" });
  fs.writeFileSync(localPath, Buffer.from(res.data));
  return textResult({ downloaded: true, name, mimeType, localPath, bytes: res.data.byteLength });
}

async function handleUploadFile({ localPath, name, folderId, mimeType }) {
  if (!fs.existsSync(localPath)) {
    return { content: [{ type: "text", text: `Error: File not found: ${localPath}` }], isError: true };
  }

  const fileName = name || path.basename(localPath);
  const stat = fs.statSync(localPath);

  const res = await drive.files.create({
    requestBody: {
      name: fileName,
      parents: folderId ? [folderId] : undefined,
    },
    media: {
      mimeType: mimeType || "application/octet-stream",
      body: fs.createReadStream(localPath),
    },
    fields: FILE_FIELDS,
  });
  return textResult({ uploaded: true, localPath, bytes: stat.size, file: res.data });
}

// ── Dispatcher ───────────────────────────────────────────────────────

const HANDLERS = {
  search: handleSearch,
  list_folder: handleListFolder,
  read_file: handleReadFile,
  read_file_metadata: handleReadFileMetadata,
  create_file: handleCreateFile,
  update_file: handleUpdateFile,
  create_folder: handleCreateFolder,
  move_file: handleMoveFile,
  copy_file: handleCopyFile,
  delete_file: handleDeleteFile,
  download_file: handleDownloadFile,
  upload_file: handleUploadFile,
};

// ── MCP Server ───────────────────────────────────────────────────────

const server = new Server(
  { name: "fields-gdrive", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  const handler = HANDLERS[name];
  if (!handler) {
    return { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true };
  }
  return wrap(() => handler(args || {}));
});

// ── Start ────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
