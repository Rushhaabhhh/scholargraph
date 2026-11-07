import { ProfileView } from '../../../components/ProfileView';
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ProfileView id={id} />;
}
