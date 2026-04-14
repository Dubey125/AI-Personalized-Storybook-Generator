import { useState } from "react";
import { motion } from "framer-motion";

function UploadForm({ onSubmit, loading }) {
  const [name, setName] = useState("");
  const [gender, setGender] = useState("girl");
  const [file, setFile] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!name.trim() || !file) {
      return;
    }

    await onSubmit({ name: name.trim(), gender, file });
  };

  return (
    <motion.form
      className="card upload-card"
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45 }}
    >
      <h2>Create Your Story Hero</h2>
      <p>Upload a face photo and generate personalized storybook scenes.</p>

      <label htmlFor="name">Child Name</label>
      <input
        id="name"
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Aarav"
        required
      />

      <label htmlFor="gender">Gender</label>
      <select
        id="gender"
        value={gender}
        onChange={(event) => setGender(event.target.value)}
      >
        <option value="girl">Girl</option>
        <option value="boy">Boy</option>
        <option value="child">Neutral</option>
      </select>

      <label htmlFor="file">Face Image</label>
      <input
        id="file"
        type="file"
        accept="image/*"
        onChange={(event) => setFile(event.target.files?.[0] || null)}
        required
      />

      <button type="submit" disabled={loading}>
        {loading ? "Uploading..." : "Upload Photo"}
      </button>
    </motion.form>
  );
}

export default UploadForm;
