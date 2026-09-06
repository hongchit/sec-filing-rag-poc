import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined';
import { IconButton, Popover, Typography } from '@mui/material';
import { useId, useState, type MouseEvent, type ReactNode } from 'react';
export function Help({ term, children }: { term: string; children: ReactNode }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const popoverId = useId();
  const open = Boolean(anchor);
  return (
    <>
      <IconButton
        size="small"
        aria-label={`Help: ${term}`}
        aria-controls={open ? popoverId : undefined}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={(event: MouseEvent<HTMLElement>) => setAnchor(event.currentTarget)}
      >
        <HelpOutlineIcon fontSize="inherit" />
      </IconButton>
      <Popover
        id={popoverId}
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
