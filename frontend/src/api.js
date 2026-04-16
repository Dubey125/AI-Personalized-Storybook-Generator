import axios from "axios";

const runtimeConfig = window.__APP_CONFIG__ || {};
const host = window.location.hostname;
const isLocalhost = host === "localhost" || host === "127.0.0.1";
const rawApiBaseUrl = isLocalhost
  ? (runtimeConfig.API_BASE_URL || process.env.REACT_APP_API_BASE_URL || "http://localhost:8000")
  : "";
const API_BASE_URL = rawApiBaseUrl.replace(/\/+$/, "");
const API_AUTH_TOKEN = (runtimeConfig.API_AUTH_TOKEN || process.env.REACT_APP_API_AUTH_TOKEN || "").trim();

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 600000, // Increased to 10 minutes to allow the heavy AI models to load
  headers: {
    "ngrok-skip-browser-warning": "69420",
    "Bypass-Tunnel-Reminder": "true"
  }
});

if (API_AUTH_TOKEN) {
  client.defaults.headers.common.Authorization = `Bearer ${API_AUTH_TOKEN}`;
}

export async function uploadProfile({ name, gender, file }) {
  const formData = new FormData();
  formData.append("name", name);
  formData.append("gender", gender);
  formData.append("file", file);

  const { data } = await client.post("/api/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return data;
}

export async function generatePreview({ sessionId, name, gender }) {
  const { data } = await client.post("/api/preview", null, {
    params: {
      session_id: sessionId,
      name,
      gender,
    },
  });

  return {
    ...data,
    preview_image_url: `${API_BASE_URL}${data.preview_url}`,
  };
}

export async function trainCharacter({ sessionId, name, gender, trainingMode }) {
  const { data } = await client.post("/api/train-character", null, {
    params: {
      session_id: sessionId,
      name,
      gender,
      training_mode: trainingMode,
    },
  });

  return data;
}

export async function uploadColabAdapter({ sessionId, trainingMode, adapterFile }) {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("training_mode", trainingMode);
  formData.append("adapter_file", adapterFile);

  const { data } = await client.post("/api/train-character/upload-adapter", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  if (data?.character_profile?.adapter_path) {
    data.character_profile.adapter_url = `${API_BASE_URL}${data.character_profile.adapter_path}`;
  }
  return data;
}

export async function generateStorybook({ sessionId, name, gender }) {
  const { data } = await client.post("/api/generate-storybook", null, {
    params: {
      session_id: sessionId,
      name,
      gender,
    },
  });

  return data;
}

export async function getStorybookJob(jobId) {
  const { data } = await client.get(`/api/jobs/${jobId}`);
  if (data?.result?.character_profile?.adapter_path) {
    data.result.character_profile.adapter_url = `${API_BASE_URL}${data.result.character_profile.adapter_path}`;
  }
  if (data?.result?.pdf_url) {
    data.result.pdf_download_url = `${API_BASE_URL}${data.result.pdf_url}`;
  }
  if (data?.result?.scenes) {
    data.result.scenes = data.result.scenes.map((scene) => ({
      ...scene,
      image_url: `${API_BASE_URL}${scene.image_url}`,
    }));
  }
  return data;
}

export async function getSystemStatus() {
  const { data } = await client.get("/api/system-status");
  return data;
}

export async function generateQuickImage({ prompt, sessionId }) {
  const response = await client.get("/api/generate", {
    params: {
      prompt,
      session_id: sessionId || undefined,
    },
    responseType: "blob",
  });

  return URL.createObjectURL(response.data);
}

export async function getRecentTrainingJobs(limit = 20, cursor = "") {
  const { data } = await client.get("/api/admin/training-jobs", {
    params: {
      limit,
      cursor: cursor || undefined,
    },
  });
  return data;
}
