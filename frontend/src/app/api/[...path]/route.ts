import { NextRequest, NextResponse } from 'next/server';

const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:9417';

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, await params);
}

async function handleProxy(request: NextRequest, { path }: { path: string[] }) {
  const subPath = path.join('/');
  const searchParams = request.nextUrl.searchParams.toString();
  const targetUrl = `${BACKEND_INTERNAL_URL}/api/${subPath}${searchParams ? `?${searchParams}` : ''}`;

  const headers = new Headers(request.headers);
  headers.delete('host');

  let body: ArrayBuffer | undefined;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    body = await request.arrayBuffer();
    // Let fetch calculate a new length for the proxied binary or multipart body.
    headers.delete('content-length');
    headers.delete('transfer-encoding');
  }

  try {
    const backendResponse = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      redirect: 'manual',
    });

    const responseHeaders = new Headers(backendResponse.headers);
    if (typeof backendResponse.headers.getSetCookie === 'function') {
      const cookies = backendResponse.headers.getSetCookie();
      if (cookies.length > 0) {
        responseHeaders.delete('set-cookie');
        for (const cookie of cookies) {
          responseHeaders.append('set-cookie', cookie);
        }
      }
    }

    return new NextResponse(backendResponse.body, {
      status: backendResponse.status,
      statusText: backendResponse.statusText,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { detail: 'The backend API is unavailable. Start the backend services and verify GET /api/v1/health, then retry.' },
      { status: 502 }
    );
  }
}
