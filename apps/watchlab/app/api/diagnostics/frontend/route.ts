import { NextResponse } from 'next/server';

const normalizeBiographBaseUrl = (rawValue: string | undefined): string | null => {
  if (!rawValue) {
    return null;
  }
  const trimmed = rawValue.trim();
  if (!trimmed || trimmed.includes('<') || trimmed.includes('>')) {
    return null;
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.toString().replace(/\/+$/, '');
  } catch {
    return null;
  }
};

const isPlainObject = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
};

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON request body.' }, { status: 400 });
  }

  if (!isPlainObject(payload)) {
    return NextResponse.json(
      { error: 'Frontend diagnostics payload must be an object.' },
      { status: 400 }
    );
  }

  const baseUrl = normalizeBiographBaseUrl(process.env.BIOGRAPH_API_BASE_URL);
  if (!baseUrl) {
    return NextResponse.json(
      {
        forwarded: false,
        reason: 'BIOGRAPH_API_BASE_URL not configured or invalid.'
      },
      { status: 202 }
    );
  }

  try {
    const token = process.env.BIOGRAPH_API_TOKEN?.trim();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${baseUrl}/observability/frontend-diagnostics/events`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const bodyText = await response.text().catch(() => '');
      return NextResponse.json(
        {
          forwarded: true,
          accepted: false,
          status: response.status,
          error: bodyText.slice(0, 400)
        },
        { status: 202 }
      );
    }

    return NextResponse.json({ forwarded: true, accepted: true }, { status: 202 });
  } catch (error) {
    return NextResponse.json(
      {
        forwarded: false,
        accepted: false,
        error: error instanceof Error ? error.message : 'Failed to forward diagnostics event.'
      },
      { status: 202 }
    );
  }
}
