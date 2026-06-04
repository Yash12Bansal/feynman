/** Shape of a user profile document stored at `users/{uid}` in Firestore. */
export interface UserProfile {
  readonly uid: string;
  readonly name: string;
  readonly email: string;
  readonly phone: string;
  readonly photoURL?: string | null;
  /** Set true once the name + phone collection step is done. */
  readonly profileComplete: boolean;
}
