import { Button, Stack, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import type { Research } from '../researchTypes';
export function ResearchHistory() {
  const [items, setItems] = useState<Research[]>([]);
  const [cursor, setCursor] = useState<string>();
  async function load(next?: string) {
    const response = await fetch(
      `/api/research/history?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ''}`,
    );
    const body = (await response.json()) as { items: Research[]; next_cursor?: string };
    setItems((old) => (next ? [...old, ...body.items] : body.items));
    setCursor(body.next_cursor);
  }
  useEffect(() => {
    void load();
  }, []);
  return (
    <AppShell>
      <Stack spacing={2}>
        <Typography variant="h1">Research history</Typography>
        {items.map((item) => (
          <Button
            component={Link}
            to={`/research/${item.research_id}`}
            key={item.research_id}
            sx={{ justifyContent: 'flex-start' }}
          >
            {item.ticker} · {item.question} · {item.status}
          </Button>
        ))}
        {cursor && <Button onClick={() => void load(cursor)}>Load more</Button>}
      </Stack>
    </AppShell>
  );
}
