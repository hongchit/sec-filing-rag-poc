import { Card, CardMedia, Stack, Typography } from '@mui/material';

interface FigureProps {
  src: string;
  narrowSrc?: string;
  alt: string;
  caption: string;
}

export function Figure({ src, narrowSrc, alt, caption }: FigureProps) {
  return (
    <Card component="figure" sx={{ m: 0, overflow: 'hidden' }}>
      <picture>
        {narrowSrc && <source media="(max-width: 899.95px)" srcSet={narrowSrc} />}
        <CardMedia component="img" src={src} alt={alt} sx={{ bgcolor: 'background.paper' }} />
      </picture>
      <Stack component="figcaption" sx={{ px: 2, py: 1.5 }}>
        <Typography variant="caption" color="text.secondary">
          {caption}
        </Typography>
      </Stack>
    </Card>
  );
}
