'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';

import styles from './FollowButton.module.css';
import { Button } from '@/components/ui/Button/Button';
import { followTopic, unfollowTopic } from '@/lib/api/user';
import { usePrefs } from '@/lib/hooks/usePrefs';

export function FollowButton({
  topicId,
  initialIsFollowed,
}: {
  topicId: string;
  initialIsFollowed?: boolean | null;
}) {
  const qc = useQueryClient();
  const prefs = usePrefs();

  const isFollowed = prefs.data
    ? (prefs.data.prefs.followed_topic_ids || []).includes(topicId)
    : Boolean(initialIsFollowed);

  const mutation = useMutation({
    mutationFn: async (next: boolean) => {
      if (next) return await followTopic(topicId);
      return await unfollowTopic(topicId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prefs'] });
      qc.invalidateQueries({ queryKey: ['topics'] });
    },
  });

  const next = mutation.variables ?? isFollowed;

  return (
    <div className={styles.wrap}>
      <Button
        variant={next ? 'secondary' : 'primary'}
        size="sm"
        isLoading={mutation.isPending}
        onClick={() => mutation.mutate(!next)}
      >
        {next ? 'Following' : 'Follow'}
      </Button>
    </div>
  );
}
