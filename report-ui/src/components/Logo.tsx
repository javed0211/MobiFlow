import mark from '../assets/branding/mobiflow-mark.png'

type Props = {
  size?: number
  variant?: 'mark' | 'full'
  className?: string
}

/** MobiFlow brand mark (M + phone check). Landscape asset; height drives size. */
export function Logo({ size = 32, variant = 'mark', className }: Props) {
  void variant
  return (
    <img
      src={mark}
      alt="MobiFlow"
      title="MobiFlow"
      height={size}
      className={className}
      style={{
        height: size,
        width: 'auto',
        display: 'block',
        objectFit: 'contain',
      }}
    />
  )
}
