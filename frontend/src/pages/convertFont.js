const fs = require('fs');
const font = fs.readFileSync('./src/fonts/NanumGothic-Regular.ttf');
const b64 = font.toString('base64');
fs.writeFileSync('./src/fonts/NanumGothic.js', 'export const NanumGothicBase64 = "' + b64 + '";');
console.log('완료! 크기:', b64.length);