const express = require('express');
const sharp = require('sharp');
const multer = require('multer');

const app = express();
const upload = multer({ storage: multer.memoryStorage() });

app.use(express.json({ limit: '50mb' }));

app.get('/', (req, res) => {
  res.send('Image overlay service running! ✅');
});

app.post('/overlay', upload.single('image'), async (req, res) => {
  try {
    const text = req.body.text || 'Text implicit';

    // Acceptă imagine ca file upload SAU base64
    const imageBuffer = req.file
      ? req.file.buffer
      : Buffer.from(req.body.imageBase64, 'base64');

    const metadata = await sharp(imageBuffer).metadata();
    const imgWidth  = metadata.width  || 1080;
    const imgHeight = metadata.height || 1920;

    const fontSize     = Math.round(imgWidth * 0.048);
    const paddingX     = Math.round(imgWidth * 0.06);
    const paddingY     = Math.round(imgWidth * 0.025);
    const borderRadius = Math.round(imgWidth * 0.045);
    const lineHeight   = Math.round(fontSize * 1.3);

    // Word wrap
    function wrapText(str, maxChars) {
      const words = str.split(' ');
      const lines = [];
      let current = '';
      for (const word of words) {
        const test = current ? `${current} ${word}` : word;
        if (test.length > maxChars && current) {
          lines.push(current);
          current = word;
        } else {
          current = test;
        }
      }
      if (current) lines.push(current);
      return lines;
    }

    const maxChars = Math.floor(imgWidth * 0.034);
    const lines    = wrapText(text, maxChars);

    const textWidth = Math.round(imgWidth * 0.65);
    const boxWidth  = textWidth + paddingX * 2;
    const boxHeight = lines.length * lineHeight + paddingY * 2;

    // Centrat pe imagine
    const boxX = Math.round((imgWidth  - boxWidth)  / 2);
    const boxY = Math.round((imgHeight - boxHeight) / 2);

    function escapeXml(str) {
      return str
        .replace(/&/g,  '&amp;')
        .replace(/</g,  '&lt;')
        .replace(/>/g,  '&gt;')
        .replace(/"/g,  '&quot;');
    }

    const textLines = lines.map((line, i) => {
      const y = paddingY + fontSize + i * lineHeight;
      return `<text
        x="${boxWidth / 2}"
        y="${y}"
        font-family="Arial Black, Arial, sans-serif"
        font-size="${fontSize}px"
        font-weight="900"
        fill="#000000"
        text-anchor="middle"
        dominant-baseline="auto"
        letter-spacing="-0.5"
      >${escapeXml(line)}</text>`;
    }).join('\n');

    const svgOverlay = `<svg xmlns="http://www.w3.org/2000/svg"
      width="${boxWidth}" height="${boxHeight}">
      <defs>
        <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
          <feDropShadow dx="0" dy="4" stdDeviation="8"
            flood-color="rgba(0,0,0,0.25)"/>
        </filter>
      </defs>
      <rect x="0" y="0"
        width="${boxWidth}" height="${boxHeight}"
        rx="${borderRadius}" ry="${borderRadius}"
        fill="white" filter="url(#shadow)"/>
      ${textLines}
    </svg>`;

    const result = await sharp(imageBuffer)
      .composite([{
        input: Buffer.from(svgOverlay),
        left: boxX,
        top:  boxY,
      }])
      .jpeg({ quality: 95 })
      .toBuffer();

    res.set('Content-Type', 'image/jpeg');
    res.send(result);

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
