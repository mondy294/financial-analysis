import app from "../server/app.js";

export default function handler(request: Parameters<typeof app>[0], response: Parameters<typeof app>[1]) {
  const currentUrl = typeof request.url === "string" ? request.url : "/";
  request.url = currentUrl.startsWith("/api") ? currentUrl : `/api${currentUrl.startsWith("/") ? currentUrl : `/${currentUrl}`}`;
  return app(request, response);
}
