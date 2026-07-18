export async function POST(): Promise<Response> {
  return Response.json(
    {
      error: "NOT_IMPLEMENTED",
      detail:
        "Web explanation pipeline là bản mock lịch sử và chưa có validator hiện hành.",
    },
    { status: 501 },
  );
}
