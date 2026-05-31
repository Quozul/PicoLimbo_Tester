/**
 * Minecraft version data derived from src/versions.py
 */

export type ProxyType = "none" | "velocity" | "bungeecord"

/**
 * Warning info for versions known to have connectivity issues.
 * onlyWithProxy: if true, the warning only applies when using that proxy type
 */
export interface VersionWarning {
  onlyWithProxy: ProxyType | null
}

export interface MinecraftVersion {
  major: number
  minor: number
  patch: number
  protocolVersion: number
  label: string
  warning?: VersionWarning
}

export const ALL_VERSIONS: MinecraftVersion[] = [
  // 1.7.x
  { major: 1, minor: 7, patch: 2, protocolVersion: 4, label: "1.7.2" },
  { major: 1, minor: 7, patch: 4, protocolVersion: 4, label: "1.7.4" },
  { major: 1, minor: 7, patch: 5, protocolVersion: 4, label: "1.7.5" },
  { major: 1, minor: 7, patch: 6, protocolVersion: 5, label: "1.7.6" },
  { major: 1, minor: 7, patch: 7, protocolVersion: 5, label: "1.7.7" },
  { major: 1, minor: 7, patch: 8, protocolVersion: 5, label: "1.7.8" },
  { major: 1, minor: 7, patch: 9, protocolVersion: 5, label: "1.7.9" },
  { major: 1, minor: 7, patch: 10, protocolVersion: 5, label: "1.7.10" },
  // 1.8.x
  { major: 1, minor: 8, patch: 0, protocolVersion: 47, label: "1.8" },
  { major: 1, minor: 8, patch: 1, protocolVersion: 47, label: "1.8.1" },
  { major: 1, minor: 8, patch: 2, protocolVersion: 47, label: "1.8.2" },
  { major: 1, minor: 8, patch: 3, protocolVersion: 47, label: "1.8.3" },
  { major: 1, minor: 8, patch: 4, protocolVersion: 47, label: "1.8.4" },
  { major: 1, minor: 8, patch: 5, protocolVersion: 47, label: "1.8.5" },
  { major: 1, minor: 8, patch: 6, protocolVersion: 47, label: "1.8.6" },
  { major: 1, minor: 8, patch: 7, protocolVersion: 47, label: "1.8.7" },
  { major: 1, minor: 8, patch: 8, protocolVersion: 47, label: "1.8.8" },
  { major: 1, minor: 8, patch: 9, protocolVersion: 47, label: "1.8.9" },
  // 1.9.x
  { major: 1, minor: 9, patch: 0, protocolVersion: 107, label: "1.9" },
  { major: 1, minor: 9, patch: 1, protocolVersion: 108, label: "1.9.1" },
  { major: 1, minor: 9, patch: 2, protocolVersion: 109, label: "1.9.2" },
  { major: 1, minor: 9, patch: 3, protocolVersion: 110, label: "1.9.3" },
  { major: 1, minor: 9, patch: 4, protocolVersion: 110, label: "1.9.4" },
  // 1.10.x
  { major: 1, minor: 10, patch: 0, protocolVersion: 210, label: "1.10" },
  { major: 1, minor: 10, patch: 1, protocolVersion: 210, label: "1.10.1" },
  { major: 1, minor: 10, patch: 2, protocolVersion: 210, label: "1.10.2" },
  // 1.11.x
  { major: 1, minor: 11, patch: 0, protocolVersion: 315, label: "1.11" },
  { major: 1, minor: 11, patch: 1, protocolVersion: 316, label: "1.11.1" },
  { major: 1, minor: 11, patch: 2, protocolVersion: 316, label: "1.11.2" },
  // 1.12.x
  { major: 1, minor: 12, patch: 0, protocolVersion: 335, label: "1.12" },
  { major: 1, minor: 12, patch: 1, protocolVersion: 338, label: "1.12.1" },
  { major: 1, minor: 12, patch: 2, protocolVersion: 340, label: "1.12.2" },
  // 1.13.x
  { major: 1, minor: 13, patch: 0, protocolVersion: 393, label: "1.13" },
  { major: 1, minor: 13, patch: 1, protocolVersion: 401, label: "1.13.1" },
  { major: 1, minor: 13, patch: 2, protocolVersion: 404, label: "1.13.2" },
  // 1.14.x
  { major: 1, minor: 14, patch: 0, protocolVersion: 477, label: "1.14" },
  { major: 1, minor: 14, patch: 1, protocolVersion: 480, label: "1.14.1" },
  { major: 1, minor: 14, patch: 2, protocolVersion: 485, label: "1.14.2" },
  { major: 1, minor: 14, patch: 3, protocolVersion: 490, label: "1.14.3" },
  { major: 1, minor: 14, patch: 4, protocolVersion: 498, label: "1.14.4" },
  // 1.15.x
  { major: 1, minor: 15, patch: 0, protocolVersion: 573, label: "1.15" },
  { major: 1, minor: 15, patch: 1, protocolVersion: 575, label: "1.15.1" },
  { major: 1, minor: 15, patch: 2, protocolVersion: 578, label: "1.15.2" },
  // 1.16.x
  { major: 1, minor: 16, patch: 0, protocolVersion: 735, label: "1.16" },
  { major: 1, minor: 16, patch: 1, protocolVersion: 736, label: "1.16.1" },
  { major: 1, minor: 16, patch: 2, protocolVersion: 751, label: "1.16.2" },
  { major: 1, minor: 16, patch: 3, protocolVersion: 753, label: "1.16.3" },
  {
    major: 1,
    minor: 16,
    patch: 4,
    protocolVersion: 754,
    label: "1.16.4",
    warning: { onlyWithProxy: null },
  },
  {
    major: 1,
    minor: 16,
    patch: 5,
    protocolVersion: 754,
    label: "1.16.5",
    warning: { onlyWithProxy: null },
  },
  // 1.17.x
  { major: 1, minor: 17, patch: 0, protocolVersion: 755, label: "1.17" },
  { major: 1, minor: 17, patch: 1, protocolVersion: 756, label: "1.17.1" },
  // 1.18.x
  { major: 1, minor: 18, patch: 0, protocolVersion: 757, label: "1.18" },
  { major: 1, minor: 18, patch: 1, protocolVersion: 757, label: "1.18.1" },
  { major: 1, minor: 18, patch: 2, protocolVersion: 758, label: "1.18.2" },
  // 1.19.x
  {
    major: 1,
    minor: 19,
    patch: 0,
    protocolVersion: 759,
    label: "1.19",
    warning: { onlyWithProxy: "velocity" },
  },
  {
    major: 1,
    minor: 19,
    patch: 1,
    protocolVersion: 760,
    label: "1.19.1",
    warning: { onlyWithProxy: "velocity" },
  },
  {
    major: 1,
    minor: 19,
    patch: 2,
    protocolVersion: 760,
    label: "1.19.2",
    warning: { onlyWithProxy: "velocity" },
  },
  { major: 1, minor: 19, patch: 3, protocolVersion: 761, label: "1.19.3" },
  { major: 1, minor: 19, patch: 4, protocolVersion: 762, label: "1.19.4" },
  // 1.20.x
  { major: 1, minor: 20, patch: 0, protocolVersion: 763, label: "1.20" },
  { major: 1, minor: 20, patch: 1, protocolVersion: 763, label: "1.20.1" },
  { major: 1, minor: 20, patch: 2, protocolVersion: 764, label: "1.20.2" },
  { major: 1, minor: 20, patch: 3, protocolVersion: 765, label: "1.20.3" },
  { major: 1, minor: 20, patch: 4, protocolVersion: 765, label: "1.20.4" },
  { major: 1, minor: 20, patch: 5, protocolVersion: 766, label: "1.20.5" },
  { major: 1, minor: 20, patch: 6, protocolVersion: 766, label: "1.20.6" },
  // 1.21.x
  { major: 1, minor: 21, patch: 0, protocolVersion: 767, label: "1.21" },
  { major: 1, minor: 21, patch: 1, protocolVersion: 767, label: "1.21.1" },
  { major: 1, minor: 21, patch: 2, protocolVersion: 768, label: "1.21.2" },
  { major: 1, minor: 21, patch: 3, protocolVersion: 768, label: "1.21.3" },
  { major: 1, minor: 21, patch: 4, protocolVersion: 769, label: "1.21.4" },
  { major: 1, minor: 21, patch: 5, protocolVersion: 770, label: "1.21.5" },
  { major: 1, minor: 21, patch: 6, protocolVersion: 771, label: "1.21.6" },
  { major: 1, minor: 21, patch: 7, protocolVersion: 772, label: "1.21.7" },
  { major: 1, minor: 21, patch: 8, protocolVersion: 772, label: "1.21.8" },
  { major: 1, minor: 21, patch: 9, protocolVersion: 773, label: "1.21.9" },
  { major: 1, minor: 21, patch: 10, protocolVersion: 773, label: "1.21.10" },
  { major: 1, minor: 21, patch: 11, protocolVersion: 774, label: "1.21.11" },
  // 26.x (PicoLimbo versions)
  { major: 26, minor: 1, patch: 0, protocolVersion: 775, label: "26.1" },
  { major: 26, minor: 1, patch: 1, protocolVersion: 775, label: "26.1.1" },
  { major: 26, minor: 1, patch: 2, protocolVersion: 775, label: "26.1.2" },
]

export const GROUPED_VERSIONS = ALL_VERSIONS.reduce<
  Record<string, MinecraftVersion[]>
>((acc, v) => {
  const group = v.major === 1 ? `1.${v.minor}` : `${v.major}.${v.minor}`
  if (!acc[group]) acc[group] = []
  acc[group].push(v)
  return acc
}, {})

export const VERSION_GROUPS = Object.keys(GROUPED_VERSIONS).sort((a, b) => {
  const [aMajor, aMinor] = a.split(".").map(Number)
  const [bMajor, bMinor] = b.split(".").map(Number)
  if (aMajor !== bMajor) return aMajor - bMajor
  return aMinor - bMinor
})

export const ALL_VERSION_LABELS = ALL_VERSIONS.map((v) => v.label)
