import LockOutlined from '@mui/icons-material/LockOutlined';
import { List, ListItemButton, ListItemIcon, ListItemText, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export type SectionNavigationItem = {
  label: string;
  href?: string;
  to?: string;
  active?: boolean;
  nested?: boolean;
  locked?: boolean;
};

export function SectionNavigation({
  label,
  items,
}: {
  label: string;
  items: SectionNavigationItem[];
}) {
  return (
    <List component="nav" aria-label={label} sx={{ position: { md: 'sticky' }, top: 24, py: 0 }}>
      <Typography variant="overline" color="text.secondary" sx={{ px: 2 }}>
        {label}
      </Typography>
      {items.map((item) => (
        <ListItemButton
          key={item.to || item.href}
          component={item.to ? RouterLink : 'a'}
          to={item.to}
          href={item.href}
          selected={item.active}
          aria-current={item.active ? 'page' : undefined}
          sx={{ pl: item.nested ? 4 : 2 }}
        >
          {item.locked && (
            <ListItemIcon sx={{ minWidth: 28 }}>
              <LockOutlined fontSize="small" aria-label="Sign-in required" />
            </ListItemIcon>
          )}
          <ListItemText primary={item.label} />
        </ListItemButton>
      ))}
    </List>
  );
}
