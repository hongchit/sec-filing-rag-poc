import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined';
import { IconButton, Popover, Typography } from '@mui/material';
import { useState, type MouseEvent, type ReactNode } from 'react';
export function Help({ term, children }: { term: string; children: ReactNode }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = Boolean(anchor);
  return (
    <>
      <IconButton
        size="small"
        aria-label={`Help: ${term}`}
        aria-expanded={open}
        onClick={(event: MouseEvent<HTMLElement>) => setAnchor(event.currentTarget)}
      >
        <HelpOutlineIcon fontSize="inherit" />
      </IconButton>
      <Popover
        open={open}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Typography sx={{ p: 2, maxWidth: 320 }}>{children}</Typography>
      </Popover>
    </>
  );
}
