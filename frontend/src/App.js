import { useEffect, useState } from "react";
import UploadForm from "./components/UploadForm";
import PreviewCard from "./components/PreviewCard";
import {
  uploadProfile,
  trainCharacter,
  uploadColabAdapter,
  generatePreview,
  generateQuickImage,
  generateStorybook,
  getStorybookJob,
  getRecentTrainingJobs,
  getSystemStatus,
 } from "./api";
import ErrorBoundary from "./components/ErrorBoundary";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function App() {
  const [loading, setLoading] = useState(false);
  const [trainingLoading, setTrainingLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [fullGenerationLoading, setFullGenerationLoading] = useState(false);
  const [statusText, setStatusText] = useState("Upload a face photo to begin.");
  const [previewUrl, setPreviewUrl] = useState("");
  const [error, setError] = useState("");
  const [sessionMeta, setSessionMeta] = useState(null);
  const [trainingMode, setTrainingMode] = useState("embedding_seed");
  const [characterProfile, setCharacterProfile] = useState(null);
  const [adapterFile, setAdapterFile] = useState(null);
  const [adapterUploadLoading, setAdapterUploadLoading] = useState(false);
  const [generatedScenes, setGeneratedScenes] = useState([]);
  const [pdfUrl, setPdfUrl] = useState("");
  const [systemStatus, setSystemStatus] = useState(null);
  const [quickPrompt, setQuickPrompt] = useState("storybook child in jungle, cartoon style");
  const [quickLoading, setQuickLoading] = useState(false);
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  const [adminJobs, setAdminJobs] = useState([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminLimit, setAdminLimit] = useState(20);
  const [adminNextCursor, setAdminNextCursor] = useState("");

  useEffect(() => {
    getSystemStatus()
      .then((status) => setSystemStatus(status))
      .catch(() => setSystemStatus(null));
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrl && previewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const pollJobUntilComplete = async ({ jobId, maxAttempts = 80 }) => {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const delayMs = Math.min(8000, 1500 + attempt * 150);
      await wait(delayMs);
      const job = await getStorybookJob(jobId);
      if (job.status === "completed") {
        return job;
      }
      if (job.status === "failed") {
        throw new Error(job.error || "Job failed");
      }
      setStatusText(`Job ${job.status || "running"} (${attempt + 1}/${maxAttempts})...`);
    }

    throw new Error("Timed out waiting for job completion.");
  };

  const handleUpload = async ({ name, gender, file }) => {
    setLoading(true);
    setError("");
    setPreviewUrl("");
    setGeneratedScenes([]);
    setPdfUrl("");
    setCharacterProfile(null);

    try {
      setStatusText("Uploading image...");
      const uploadResponse = await uploadProfile({ name, gender, file });
      setSessionMeta({
        sessionId: uploadResponse.session_id,
        name,
        gender,
      });
      setCharacterProfile(uploadResponse.character_profile || null);
      setStatusText("Upload complete. Next step: train character profile.");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail || "Something went wrong while uploading.");
      setStatusText("Try again with another clear face image.");
    } finally {
      setLoading(false);
    }
  };

  const handleTrainCharacter = async () => {
    if (!sessionMeta) {
      return;
    }

    setTrainingLoading(true);
    setError("");

    try {
      setStatusText("Queueing character training...");
      const response = await trainCharacter({
        sessionId: sessionMeta.sessionId,
        name: sessionMeta.name,
        gender: sessionMeta.gender,
        trainingMode,
      });

      const jobId = response?.job_id;
      if (!jobId) {
        throw new Error("Failed to start character training job.");
      }

      const job = await pollJobUntilComplete({ jobId, maxAttempts: 90 });
      setCharacterProfile(job?.result?.character_profile || null);
      setStatusText("Character profile is ready. Next step: generate preview.");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail || requestError?.message;
      setError(detail || "Failed to train character profile.");
      setStatusText("Training failed. Please try again.");
    } finally {
      setTrainingLoading(false);
    }
  };

  const handleGeneratePreview = async () => {
    if (!sessionMeta) {
      return;
    }

    setPreviewLoading(true);
    setError("");

    try {
      setStatusText("Generating preview image...");
      const previewResponse = await generatePreview({
        sessionId: sessionMeta.sessionId,
        name: sessionMeta.name,
        gender: sessionMeta.gender,
      });

      setPreviewUrl(previewResponse.preview_image_url);
      setCharacterProfile(previewResponse.character_profile || characterProfile);
      setStatusText("Preview generated. Next step: generate full storybook.");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail || "Something went wrong while generating the preview.");
      setStatusText("Preview generation failed. Please try again.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleUploadColabAdapter = async () => {
    if (!sessionMeta || !adapterFile) {
      return;
    }

    setAdapterUploadLoading(true);
    setError("");
    try {
      setStatusText("Uploading Colab-trained adapter...");
      const response = await uploadColabAdapter({
        sessionId: sessionMeta.sessionId,
        trainingMode,
        adapterFile,
      });
      setCharacterProfile(response?.character_profile || null);
      setStatusText("Adapter uploaded. Next step: generate preview.");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail || requestError?.message;
      setError(detail || "Failed to upload adapter.");
      setStatusText("Adapter upload failed. Please verify your file and try again.");
    } finally {
      setAdapterUploadLoading(false);
    }
  };

  const handleGenerateFullStorybook = async () => {
    if (!sessionMeta) {
      return;
    }

    setFullGenerationLoading(true);
    setError("");

    try {
      setStatusText("Queueing storybook generation job...");
      const response = await generateStorybook({
        sessionId: sessionMeta.sessionId,
        name: sessionMeta.name,
        gender: sessionMeta.gender,
      });

      const jobId = response?.job_id;
      if (!jobId) {
        throw new Error("Failed to start job.");
      }

      const job = await pollJobUntilComplete({ jobId, maxAttempts: 80 });
      const result = job.result || {};
      setGeneratedScenes(result.scenes || []);
      setPdfUrl(result.pdf_download_url || "");
      setStatusText("Full storybook generated successfully.");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail || requestError?.message;
      setError(detail || "Failed to generate full storybook.");
      setStatusText("Generation failed. Please try again.");
    } finally {
      setFullGenerationLoading(false);
    }
  };

  const handleQuickGenerate = async () => {
    setQuickLoading(true);
    setError("");
    try {
      setStatusText("Generating quick image from backend model...");
      const imageUrl = await generateQuickImage({
        prompt: quickPrompt,
        sessionId: sessionMeta?.sessionId,
      });
      if (previewUrl && previewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(previewUrl);
      }
      setPreviewUrl(imageUrl);
      setStatusText("Quick image generated successfully.");
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail || requestError?.message;
      setError(detail || "Quick generation failed.");
      setStatusText("Quick generation failed. Please try again.");
    } finally {
      setQuickLoading(false);
    }
  };

  const handleLoadTrainingJobs = async (reset = true) => {
    setAdminLoading(true);
    try {
      const cursor = reset ? "" : adminNextCursor;
      const response = await getRecentTrainingJobs(adminLimit, cursor);
      const nextItems = response?.items || [];
      setAdminJobs((prev) => (reset ? nextItems : [...prev, ...nextItems]));
      setAdminNextCursor(response?.next_cursor || "");
    } catch {
      if (reset) {
        setAdminJobs([]);
      }
    } finally {
      setAdminLoading(false);
    }
  };

  return (
    <main className="page-wrap">
      <header className="hero">
        <p className="eyebrow">Personalized AI Storybook Generator</p>
        <h1>Turn a Face Photo Into a Magical Story Hero</h1>
        <p className="subhead">
          Upload once, preview instantly, then generate a full illustrated storybook.
        </p>
        {systemStatus && (
          <>
            <p className="subhead">
              Backend status: {systemStatus.status}, identity mode: {systemStatus.identity_mode},
              device: {systemStatus.model_device}, runtime: {systemStatus.model_runtime || "unknown"}
            </p>
            {systemStatus.model_runtime && systemStatus.model_runtime !== "full-diffusers" && (
              <p className="runtime-warning">
                Running in fallback mode. Outputs stay personalized from your uploaded photo, but full AI quality requires diffusers/torch runtime.
              </p>
            )}
          </>
        )}
      </header>

      <section className="content-grid">
        <UploadForm onSubmit={handleUpload} loading={loading} />
        <PreviewCard previewUrl={previewUrl} statusText={statusText} error={error} />
      </section>

      <section className="card result-card">
        <h2>Train Character Profile</h2>
        <p>Choose a consistency mode before preview/story generation.</p>
        <label htmlFor="training-mode">Training Mode</label>
        <select
          id="training-mode"
          value={trainingMode}
          onChange={(event) => setTrainingMode(event.target.value)}
          disabled={!sessionMeta || trainingLoading || previewLoading || fullGenerationLoading}
        >
          <option value="embedding_seed">Embedding Seed (fast)</option>
          <option value="lora">LoRA (adapter training)</option>
          <option value="dreambooth">DreamBooth (adapter training)</option>
        </select>
        <button
          type="button"
          onClick={handleTrainCharacter}
          disabled={!sessionMeta || trainingLoading}
        >
          {trainingLoading ? "Training Character..." : "Train Character"}
        </button>

        <label htmlFor="adapter-file">Or Upload Colab Adapter</label>
        <input
          id="adapter-file"
          type="file"
          accept=".safetensors,.bin,.pt,.ckpt"
          onChange={(event) => setAdapterFile(event.target.files?.[0] || null)}
          disabled={!sessionMeta || adapterUploadLoading}
        />
        <button
          type="button"
          onClick={handleUploadColabAdapter}
          disabled={!sessionMeta || !adapterFile || adapterUploadLoading}
        >
          {adapterUploadLoading ? "Uploading Adapter..." : "Upload Colab Adapter"}
        </button>

        {characterProfile && (
          <>
            <p className="subhead">
              Profile status: {characterProfile.status || "ready"}, mode: {characterProfile.consistency_method || "embedding_seed"}
            </p>
            {characterProfile.adapter_url && (
              <p className="subhead">
                Adapter artifact: <a href={characterProfile.adapter_url} target="_blank" rel="noreferrer">open</a>
              </p>
            )}
            {typeof characterProfile.training_duration_seconds === "number" && (
              <p className="subhead">
                Training duration: {characterProfile.training_duration_seconds}s
              </p>
            )}
            {typeof characterProfile.artifact_size_bytes === "number" && characterProfile.artifact_size_bytes > 0 && (
              <p className="subhead">
                Artifact size: {characterProfile.artifact_size_bytes} bytes
              </p>
            )}
          </>
        )}
      </section>

      <section className="card result-card">
        <h2>Generate Preview</h2>
        <p>Generate a visual check before full storybook rendering.</p>
        <button
          type="button"
          onClick={handleGeneratePreview}
          disabled={!sessionMeta || previewLoading || fullGenerationLoading}
        >
          {previewLoading ? "Generating Preview..." : "Generate Preview"}
        </button>
      </section>

      <section className="card result-card">
        <h2>Generate Full Storybook</h2>
        <p>After preview approval, generate all scene illustrations and a PDF storybook.</p>
        <button
          type="button"
          onClick={handleGenerateFullStorybook}
          disabled={!sessionMeta || !previewUrl || fullGenerationLoading}
        >
          {fullGenerationLoading ? "Building Storybook..." : "Generate 5-Scene Storybook"}
        </button>

        {pdfUrl && (
          <p className="download-link-wrap">
            <a href={pdfUrl} target="_blank" rel="noreferrer">
              Download Storybook PDF
            </a>
          </p>
        )}

        {!!generatedScenes.length && (
          <div className="scene-grid">
            {generatedScenes.map((scene, index) => (
              <article className="scene-card" key={`${scene.title}-${index}`}>
                <img src={scene.image_url} alt={scene.title} />
                <h3>{scene.title}</h3>
                <p>{scene.story_text}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="card result-card">
        <h2>Quick Generate (Single API Call)</h2>
        <p>
          Test your uploaded LoRA model directly. If a session exists, backend also reuses that identity seed.
        </p>
        <label htmlFor="quick-prompt">Prompt</label>
        <input
          id="quick-prompt"
          type="text"
          value={quickPrompt}
          onChange={(event) => setQuickPrompt(event.target.value)}
          placeholder="storybook child in jungle, cartoon style"
          maxLength={500}
        />
        <button
          type="button"
          onClick={handleQuickGenerate}
          disabled={quickLoading}
        >
          {quickLoading ? "Generating..." : "Generate Quick Image"}
        </button>
      </section>

      <section className="card result-card">
        <h2>Training Admin</h2>
        <p>Inspect the most recent character training jobs.</p>
        <div className="admin-actions">
          <button
            type="button"
            onClick={() => setShowAdminPanel((prev) => !prev)}
          >
            {showAdminPanel ? "Hide Training Jobs" : "Show Training Jobs"}
          </button>
          {showAdminPanel && (
            <>
              <select
                value={adminLimit}
                onChange={(event) => setAdminLimit(Number(event.target.value))}
                disabled={adminLoading}
                aria-label="Admin page size"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
              <button
                type="button"
                onClick={() => handleLoadTrainingJobs(true)}
                disabled={adminLoading}
              >
                {adminLoading ? "Refreshing..." : "Refresh"}
              </button>
            </>
          )}
        </div>

        {showAdminPanel && (
          <div className="admin-jobs-wrap">
            {!adminJobs.length && !adminLoading && (
              <p className="subhead">No recent training jobs found.</p>
            )}
            {adminJobs.map((job) => (
              <article className="admin-job-card" key={job.job_id}>
                <p><strong>Job:</strong> {job.job_id}</p>
                <p><strong>Status:</strong> {job.status}</p>
                <p><strong>Mode:</strong> {job.training_mode || "n/a"}</p>
                <p><strong>Session:</strong> {job.session_id || "n/a"}</p>
                <p><strong>Duration:</strong> {job.training_duration_seconds ?? "n/a"}</p>
                <p><strong>Artifact Bytes:</strong> {job.artifact_size_bytes ?? 0}</p>
                {job.artifact_path && <p><strong>Artifact Path:</strong> {job.artifact_path}</p>}
                {job.error && <p className="error-text"><strong>Error:</strong> {job.error}</p>}
              </article>
            ))}
            {!!adminJobs.length && !!adminNextCursor && (
              <button
                type="button"
                onClick={() => handleLoadTrainingJobs(false)}
                disabled={adminLoading}
              >
                {adminLoading ? "Loading..." : "Load More"}
              </button>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

function AppWithErrorBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}

export default AppWithErrorBoundary;
