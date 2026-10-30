import { useState } from 'react';
import { displayName, type User } from '../../auth/AuthProvider';
import './UserAvatar.css';

export default function UserAvatar({ user }: { user: User }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const initials = displayName(user).split(/\s+/).slice(0, 2).map((part) => Array.from(part)[0]).join('').toUpperCase();
  return user.photo_url && failedUrl !== user.photo_url
    ? <img className="user-avatar" src={user.photo_url} alt="" referrerPolicy="no-referrer" onError={() => setFailedUrl(user.photo_url)} />
    : <span className="user-avatar user-avatar--fallback" aria-hidden="true">{initials}</span>;
}
