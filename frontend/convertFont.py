import base64 
 
with open('src/fonts/NanumGothic-Regular.ttf', 'rb') as f: 
    data = base64.b64encode(f.read()).decode() 
 
with open('src/fonts/NanumGothic.js', 'w') as f: 
    f.write('export const NanumGothicBase64 = "' + data + '";') 
 
print('완료! 크기:', len(data)) 
