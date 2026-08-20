// Shared canvas geometry: screen/world conversion, zoom limits, and drag helpers
// used by Canvas and the item components.

import type { ViewState } from '../../types'

export const MIN_SCALE = 0.2
export const MAX_SCALE = 4

// Largest edge an image is given when first placed, in world units.
export const MAX_IMAGE_EDGE = 480

export const MIN_ITEM_WIDTH = 80
export const MIN_ITEM_HEIGHT = 40

export function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale))
}

// The world extends downward from y=0, so panning never reveals space above the top.
export function clampPanY(panY: number): number {
  return Math.min(0, panY)
}

export interface ScreenPoint {
  x: number
  y: number
}

export function screenToWorld(point: ScreenPoint, view: ViewState): ScreenPoint {
  return {
    x: (point.x - view.pan_x) / view.scale,
    y: (point.y - view.pan_y) / view.scale,
  }
}

// Pointer position relative to an element's top-left corner.
export function pointerInElement(
  event: { clientX: number; clientY: number },
  element: HTMLElement,
): ScreenPoint {
  const rect = element.getBoundingClientRect()
  return { x: event.clientX - rect.left, y: event.clientY - rect.top }
}

// Scales an image down to fit MAX_IMAGE_EDGE, preserving aspect ratio.
export function fitImage(width: number, height: number): { width: number; height: number } {
  const longest = Math.max(width, height)
  if (longest <= MAX_IMAGE_EDGE) return { width, height }
  const factor = MAX_IMAGE_EDGE / longest
  return { width: Math.round(width * factor), height: Math.round(height * factor) }
}

// Reads the intrinsic dimensions of an image blob, already fitted to the canvas.
export function readImageSize(blob: Blob): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob)
    const probe = new Image()
    probe.onload = () => {
      URL.revokeObjectURL(url)
      resolve(fitImage(probe.naturalWidth, probe.naturalHeight))
    }
    probe.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Could not read image dimensions'))
    }
    probe.src = url
  })
}

// First image file in a clipboard or drop payload, if any.
export function imageFileFrom(data: DataTransfer | null): File | null {
  if (!data) return null
  for (const file of Array.from(data.files)) {
    if (file.type.startsWith('image/')) return file
  }
  for (const entry of Array.from(data.items)) {
    if (entry.kind === 'file' && entry.type.startsWith('image/')) {
      const file = entry.getAsFile()
      if (file) return file
    }
  }
  return null
}
