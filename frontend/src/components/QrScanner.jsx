import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { Camera, ImageUp } from "lucide-react";
import { Modal } from "./ui";

/** Extract a ProofPulse ID from a scanned QR payload (URL or bare id). */
export function idFromPayload(text) {
  const m = /PP-[A-Z2-9]{10}/i.exec(text || "");
  return m ? m[0].toUpperCase() : null;
}

export default function QrScanner({ open, onClose, onResult }) {
  const video = useRef(null);
  const canvas = useRef(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let stream; let raf; let stopped = false;
    setError("");
    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) { setError("Camera access is not available here. Upload a QR image instead."); return; }
      setStarting(true);
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
        video.current.srcObject = stream;
        await video.current.play();
        setStarting(false);
        const tick = () => {
          const v = video.current; const c = canvas.current;
          if (v && c && v.readyState === v.HAVE_ENOUGH_DATA) {
            c.width = v.videoWidth; c.height = v.videoHeight;
            const ctx = c.getContext("2d", { willReadFrequently: true });
            ctx.drawImage(v, 0, 0);
            const img = ctx.getImageData(0, 0, c.width, c.height);
            const code = jsQR(img.data, img.width, img.height);
            const id = code && idFromPayload(code.data);
            if (id) { onResult(id); return; }
          }
          raf = requestAnimationFrame(tick);
        };
        tick();
      } catch {
        setStarting(false);
        setError("Could not open the camera (permission denied or no camera). You can upload a QR image instead.");
      }
    })();
    return () => { stopped = true; cancelAnimationFrame(raf); stream?.getTracks().forEach((t) => t.stop()); };
  }, [open, onResult]);

  const fromImage = (file) => {
    if (!file) return;
    const img = new Image();
    img.onload = () => {
      const c = canvas.current; c.width = img.width; c.height = img.height;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(img, 0, 0);
      const data = ctx.getImageData(0, 0, c.width, c.height);
      const code = jsQR(data.data, data.width, data.height);
      const id = code && idFromPayload(code.data);
      if (id) onResult(id); else setError("No ProofPulse QR code found in that image.");
      URL.revokeObjectURL(img.src);
    };
    img.src = URL.createObjectURL(file);
  };

  return (
    <Modal open={open} onClose={onClose} title="Scan a ProofPulse QR code">
      <div className="col">
        <video ref={video} className="scan-video" muted playsInline aria-label="Camera preview" />
        <canvas ref={canvas} hidden />
        {starting && <div className="small muted"><Camera size={14} /> Starting camera…</div>}
        {error && <div className="err">{error}</div>}
        <div className="row between">
          <label className="btn sm" style={{ cursor: "pointer" }}><ImageUp size={16} /> Upload QR image
            <input type="file" accept="image/*" hidden onChange={(e) => fromImage(e.target.files[0])} />
          </label>
          <button className="btn sm ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </Modal>
  );
}
