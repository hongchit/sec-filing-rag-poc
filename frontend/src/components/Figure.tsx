import { Card, CardMedia, Stack, Typography } from '@mui/material';

export function Figure({ src, alt, caption }: { src: string; alt: string; caption: string }) {
  return (
    <Card component="figure" sx={{ m: 0, overflow: 'hidden' }}>
      <CardMedia component="img" src={src} alt={alt} sx={{ bgcolor: 'background.paper' }} />
      <Stack component="figcaption" sx={{ px: 2, py: 1.5 }}>
        <Typography variant="caption" color="text.secondary">
          {caption}
        </Typography>
      </Stack>
    </Card>
  );
}
