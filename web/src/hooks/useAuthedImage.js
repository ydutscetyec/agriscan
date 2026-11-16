import { useEffect, useState } from 'react'
import { fetchImageObjectUrl } from '../api/client'

/** Load a protected image through an authenticated fetch. Returns { src, failed }. */
export function useAuthedImage(imageId) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!imageId) return undefined
    let url = null
    let cancelled = false
    setSrc(null)
    setFailed(false)
    fetchImageObjectUrl(imageId)
      .then((objectUrl) => {
        if (cancelled) { URL.revokeObjectURL(objectUrl); return }
        url = objectUrl
        setSrc(objectUrl)
      })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [imageId])

  return { src, failed }
}
