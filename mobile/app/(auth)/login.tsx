import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { router } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { saveTokens } from '@/lib/auth';
import { loginUser, extractErrorMessage } from '@/lib/auth-api';
import { loginSchema, LoginFormValues } from '@/lib/validation';

export default function LoginScreen() {
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: LoginFormValues) => {
    setSubmitError(null);
    try {
      const { access_token, refresh_token } = await loginUser(values);
      await saveTokens(access_token, refresh_token);
      router.replace('/');
    } catch (error) {
      setSubmitError(extractErrorMessage(error, 'Invalid email or password.'));
    }
  };

  return (
    <View style={styles.container}>
      <ThemedView style={styles.form}>
        <ThemedText type="title">Log In</ThemedText>

        <Controller
          control={control}
          name="email"
          render={({ field: { onChange, onBlur, value } }) => (
            <TextInput
              style={styles.input}
              autoCapitalize="none"
              keyboardType="email-address"
              placeholder="Email"
              onBlur={onBlur}
              onChangeText={onChange}
              value={value}
              testID="login-email"
            />
          )}
        />
        {errors.email ? <ThemedText style={styles.errorText}>{errors.email.message}</ThemedText> : null}

        <Controller
          control={control}
          name="password"
          render={({ field: { onChange, onBlur, value } }) => (
            <TextInput
              style={styles.input}
              secureTextEntry
              autoCapitalize="none"
              placeholder="Password"
              onBlur={onBlur}
              onChangeText={onChange}
              value={value}
              testID="login-password"
            />
          )}
        />
        {errors.password ? <ThemedText style={styles.errorText}>{errors.password.message}</ThemedText> : null}

        {submitError ? (
          <ThemedText style={styles.errorText} testID="login-submit-error">
            {submitError}
          </ThemedText>
        ) : null}

        <Pressable
          style={[styles.button, isSubmitting && styles.buttonDisabled]}
          onPress={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          testID="login-submit">
          {isSubmitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <ThemedText style={styles.buttonText}>Log In</ThemedText>
          )}
        </Pressable>

        <Pressable onPress={() => router.push('/(auth)/forgot-password')}>
          <ThemedText type="link">Forgot password?</ThemedText>
        </Pressable>
        <Pressable onPress={() => router.push('/(auth)/register')}>
          <ThemedText type="link">Need an account? Register</ThemedText>
        </Pressable>
      </ThemedView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, justifyContent: 'center' },
  form: { gap: 16 },
  input: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
  },
  errorText: { color: '#dc2626', fontSize: 13 },
  button: {
    backgroundColor: '#0a7ea4',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 16 },
});