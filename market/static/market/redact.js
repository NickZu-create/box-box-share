// Lets students black out student and ID numbers on a transcript image before it leaves their device.
// The redacted canvas replaces the chosen file, so once a box is drawn the original image is never uploaded.
(() => {
  const input = document.getElementById('proof-input');
  const box = document.getElementById('redact');
  const canvas = document.getElementById('redact-canvas');
  const undo = document.getElementById('redact-undo');
  if (!input || !canvas || !window.DataTransfer || !canvas.toBlob) return;
  let image = null, boxes = [], start = null;

  const draw = (extra) => {
    const ctx = canvas.getContext('2d');
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#000';
    for (const b of extra ? [...boxes, extra] : boxes) ctx.fillRect(b.x, b.y, b.w, b.h);
  };
  const point = (e) => {
    const r = canvas.getBoundingClientRect();
    return { x: (e.clientX - r.left) * canvas.width / r.width, y: (e.clientY - r.top) * canvas.height / r.height };
  };
  const rect = (a, b) => ({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) });
  const save = () => canvas.toBlob((blob) => {
    const files = new DataTransfer();
    files.items.add(new File([blob], 'redacted.jpg', { type: 'image/jpeg' }));
    input.files = files.files;
  }, 'image/jpeg', 0.92);

  input.addEventListener('change', () => {
    const file = input.files[0];
    box.hidden = true;
    if (!file || !file.type.startsWith('image/')) return;
    // A data: URL keeps this within the page's img-src CSP; blob: URLs are not allowed.
    const reader = new FileReader();
    reader.onload = () => {
      image = new Image();
      image.onload = () => {
        const scale = Math.min(1, 1800 / Math.max(image.width, image.height));
        canvas.width = Math.round(image.width * scale);
        canvas.height = Math.round(image.height * scale);
        boxes = [];
        draw();
        box.hidden = false;
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
  canvas.addEventListener('pointerdown', (e) => {
    if (!image) return;
    start = point(e);
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', (e) => { if (start) draw(rect(start, point(e))); });
  canvas.addEventListener('pointerup', (e) => {
    if (!start) return;
    const r = rect(start, point(e));
    start = null;
    if (r.w > 3 && r.h > 3) boxes.push(r);
    draw();
    if (boxes.length) save();
  });
  undo.addEventListener('click', () => { boxes.pop(); draw(); save(); });
})();
