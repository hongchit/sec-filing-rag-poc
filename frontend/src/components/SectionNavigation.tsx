import ChevronLeft from '@mui/icons-material/ChevronLeft';
import ChevronRight from '@mui/icons-material/ChevronRight';
import LockOutlined from '@mui/icons-material/LockOutlined';
import {
  Box,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
} from '@mui/material';
import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';

export type SectionNavigationItem = {
  label: string;
  href?: string;
  to?: string;
  active?: boolean;
  nested?: boolean;
  locked?: boolean;
};

const edgeTolerance = 2;

export function SectionNavigation({
  label,
  items,
}: {
  label: string;
  items: SectionNavigationItem[];
}) {
  const listRef = useRef<HTMLUListElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateOverflow = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    setCanScrollLeft(list.scrollLeft > edgeTolerance);
    setCanScrollRight(list.scrollLeft + list.clientWidth < list.scrollWidth - edgeTolerance);
  }, []);

  const revealActiveItem = useCallback(() => {
    const list = listRef.current;
    const activeItem = list?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!list || !activeItem) return;

    const itemContainer = activeItem.closest<HTMLElement>('li') ?? activeItem;
    const itemStart = itemContainer.offsetLeft;
    const itemEnd = itemStart + itemContainer.offsetWidth;
    const visibleStart = list.scrollLeft;
    const visibleEnd = visibleStart + list.clientWidth;
    let left: number | undefined;
    if (itemStart < visibleStart) left = itemStart;
    else if (itemEnd > visibleEnd) left = itemEnd - list.clientWidth;

    if (left !== undefined) {
      const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      list.scrollTo({ left, behavior: reduceMotion ? 'auto' : 'smooth' });
    }
  }, []);

  const activeItem = items.find((item) => item.active);
  const activeDestination = activeItem?.to ?? activeItem?.href ?? '';
  const itemSignature = items.map((item) => `${item.to ?? item.href}:${item.label}`).join('|');

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;

    const refresh = () => {
      revealActiveItem();
      updateOverflow();
    };
    refresh();
    list.addEventListener('scroll', updateOverflow, { passive: true });
    window.addEventListener('resize', refresh);
    const observer = new ResizeObserver(refresh);
    observer.observe(list);
    Array.from(list.children).forEach((child) => observer.observe(child));
    return () => {
      list.removeEventListener('scroll', updateOverflow);
      window.removeEventListener('resize', refresh);
      observer.disconnect();
    };
  }, [activeDestination, itemSignature, revealActiveItem, updateOverflow]);

  const scroll = (direction: -1 | 1) => {
    const list = listRef.current;
    if (!list) return;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    list.scrollBy({
      left: direction * Math.max(list.clientWidth * 0.9, 1),
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  };

  const cueSx = {
    position: 'absolute',
    top: 0,
    bottom: 0,
    width: 48,
    zIndex: 1,
    display: { xs: 'flex', md: 'none' },
    alignItems: 'center',
  } as const;

  return (
    <Box component="nav" aria-label={label} sx={{ position: { md: 'sticky' }, top: 24 }}>
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ px: 2, display: { xs: 'none', md: 'block' } }}
      >
        {label}
      </Typography>
      <Box sx={{ position: 'relative', minWidth: 0 }}>
        <List
          ref={listRef}
          sx={{
            py: 0,
            display: { xs: 'flex', md: 'block' },
            maxWidth: '100%',
            overflowX: { xs: 'auto', md: 'visible' },
            scrollbarWidth: 'thin',
          }}
        >
          {items.map((item) => (
            <ListItem
              disablePadding
              key={item.to || item.href}
              sx={{
                flex: { xs: '0 0 auto', md: '1 1 auto' },
                width: { xs: 'auto', md: '100%' },
              }}
            >
              <ListItemButton
                component={item.to ? RouterLink : 'a'}
                to={item.to}
                href={item.href}
                selected={item.active}
                aria-current={item.active ? 'page' : undefined}
                sx={{
                  pl: { xs: 2, md: item.nested ? 4 : 2 },
                  pr: 2,
                  whiteSpace: 'nowrap',
                }}
              >
                {item.locked && (
                  <ListItemIcon sx={{ minWidth: 28 }}>
                    <LockOutlined fontSize="small" aria-label="Sign-in required" />
                  </ListItemIcon>
                )}
                <ListItemText primary={item.label} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
        {canScrollLeft && (
          <Box
            sx={{
              ...cueSx,
              left: 0,
              justifyContent: 'flex-start',
              background: (theme) =>
                `linear-gradient(90deg, ${theme.palette.background.default} 45%, transparent)`,
            }}
          >
            <IconButton size="small" aria-label={`Scroll ${label} left`} onClick={() => scroll(-1)}>
              <ChevronLeft />
            </IconButton>
          </Box>
        )}
        {canScrollRight && (
          <Box
            sx={{
              ...cueSx,
              right: 0,
              justifyContent: 'flex-end',
              background: (theme) =>
                `linear-gradient(270deg, ${theme.palette.background.default} 45%, transparent)`,
            }}
          >
            <IconButton size="small" aria-label={`Scroll ${label} right`} onClick={() => scroll(1)}>
              <ChevronRight />
            </IconButton>
          </Box>
        )}
      </Box>
    </Box>
  );
}
