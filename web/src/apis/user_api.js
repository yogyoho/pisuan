import { apiPost } from './base'
import { rasterizeSvgFileToPng } from '@/utils/svgRasterize'

export const userApi = {
  uploadImage: async (file) => {
    // 服务端图片白名单不含 SVG，本地图标常为 SVG，先在浏览器位图化
    const payload =
      /\.svg$/i.test(file?.name || '') || file?.type === 'image/svg+xml'
        ? await rasterizeSvgFileToPng(file)
        : file
    const formData = new FormData()
    formData.append('file', payload)
    return apiPost('/api/user/upload-image', formData)
  }
}
