import { motion } from "framer-motion";

function PreviewCard({ previewUrl, statusText, error }) {
  return (
    <motion.section
      className="card preview-card"
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: 0.05 }}
    >
      <h2>Story Preview</h2>
      {!previewUrl && !error && <p>{statusText || "Your preview will appear here."}</p>}
      {error && <p className="error-text">{error}</p>}
      {previewUrl && (
        <div className="preview-image-wrap">
          <img src={previewUrl} alt="Generated story preview" />
        </div>
      )}
    </motion.section>
  );
}

export default PreviewCard;
