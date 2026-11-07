/**
 * SVG 文件位图化：后端 upload-image 只接受 PNG/JPEG/WebP/GIF（PIL 格式白名单），
 * SVG 由浏览器 canvas 栅格化为 PNG 后再上传，服务端无需引入渲染依赖，
 * 也避免同源直接伺服用户 SVG 带来的脚本执行风险。
 */
const SVG_TARGET_BOX = 512

export async function rasterizeSvgFileToPng(file, targetBox = SVG_TARGET_BOX) {
  const doc = new DOMParser().parseFromString(await file.text(), 'image/svg+xml')
  const svg = doc.documentElement
  if (!svg || svg.nodeName.toLowerCase() !== 'svg' || doc.querySelector('parsererror')) {
    throw new Error('SVG 文件解析失败，请检查文件是否有效')
  }

  // 以 viewBox 推断宽高比；无 viewBox 时退回声明宽高，再退 1:1
  const viewBox = (svg.getAttribute('viewBox') || '')
    .trim()
    .split(/[\s,]+/)
    .map(Number)
  let ratio = 1
  if (viewBox.length === 4 && viewBox[2] > 0 && viewBox[3] > 0) {
    ratio = viewBox[2] / viewBox[3]
  } else if (svg.getAttribute('width') && svg.getAttribute('height')) {
    ratio = parseFloat(svg.getAttribute('width')) / parseFloat(svg.getAttribute('height'))
  }
  if (!Number.isFinite(ratio) || ratio <= 0) ratio = 1

  const width = ratio >= 1 ? targetBox : Math.round(targetBox * ratio)
  const height = ratio >= 1 ? Math.round(targetBox / ratio) : targetBox
  svg.setAttribute('width', String(width))
  svg.setAttribute('height', String(height))

  const url = URL.createObjectURL(
    new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' })
  )
  try {
    const image = await new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('SVG 解码失败，请检查文件是否有效'))
      img.src = url
    })

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('当前浏览器不支持 Canvas 位图化')
    ctx.drawImage(image, 0, 0, width, height)

    let blob
    try {
      blob = await new Promise((resolve, reject) => {
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('PNG 编码失败'))), 'image/png')
      })
    } catch {
      // 画布被外部资源污染时 toBlob 抛 SecurityError
      throw new Error('SVG 含外部资源引用，无法位图化，请改用 PNG/JPG 图片')
    }

    return new File([blob], `${(file.name || 'icon').replace(/\.svg$/i, '')}.png`, {
      type: 'image/png'
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}
