import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { router } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, TextInput } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { registerUser, extractErrorMessage } from '@/lib/auth-api';
import { registerSchema, RegisterFormValues } from '@/lib/validation';

export default function RegisterScreen() {
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: '', email: '', phone_number: '', password: '' },
  });

  const onSubmit = async (values: RegisterFormValues) => {
    setSubmitError(null);
    try {
      await registerUser(values);
      router.push({
        pathname: '/(auth)/verify-otp',
        params: { phone_number: values.phone_number },
      });
    } catch (error) {
      setSubmitError(extractErrorMessage(error, 'Could not create your account. Please try again.'));
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <ThemedView style={styles.form}>
        <ThemedText type="title">Create Account</ThemedText>

        <Field label="Full name" error={errors.full_name?.message}>
          <Controller
            control={control}
            name="full_name"
            render={({ field: { onChange, onBlur, value } }) => (
              <TextInput
                style={styles.input}
                autoCapitalize="words"
                placeholder="Asha Rao"
                onBlur={onBlur}
                onChangeText={onChange}
                value={value}
                testID="register-full-name"
              />
            )}
          />
        </Field>

        <Field label="Email" error={errors.email?.message}>
          <Controller
            control={control}
            name="email"
            render={({ field: { onChange, onBlur, value } }) => (
              <TextInput
                style={styles.input}
                autoCapitalize="none"
                keyboardType="email-address"
                placeholder="you@example.com"
                onBlur={onBlur}
                onChangeText={onChange}
                value={value}
                testID="register-email"
              />
            )}
          />
        </Field>

        <Field label="Phone number" error={errors.phone_number?.message}>
          <Controller
            control={control}
            name="phone_number"
            render={({ field: { onChange, onBlur, value } }) => (
              <TextInput
                style={styles.input}
                autoCapitalize="none"
                keyboardType="phone-pad"
                placeholder="+919876543210"
                onBlur={onBlur}
                onChangeText={onChange}
                value={value}
                testID="register-phone"
              />
            )}
          />
        </Field>

        <Field label="Password" error={errors.password?.message}>
          <Controller
            control={control}
            name="password"
            render={({ field: { onChange, onBlur, value } }) => (
              <TextInput
                style={styles.input}
                secureTextEntry
                autoCapitalize="none"
                placeholder="At least 8 characters, 1 digit"
                onBlur={onBlur}
                onChangeText={onChange}
                value={value}
                testID="register-password"
              />
            )}
          />
        </Field>

        {submitError ? (
          <ThemedText style={styles.errorText} testID="register-submit-error">
            {submitError}
          </ThemedText>
        ) : null}

        <Pressable
          style={[styles.button, isSubmitting && styles.buttonDisabled]}
          onPress={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          testID="register-submit">
          {isSubmitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <ThemedText style={styles.buttonText}>Create Account</ThemedText>
          )}
        </Pressable>

        <Pressable onPress={() => router.push('/(auth)/login')}>
          <ThemedText type="link">Already have an account? Log in</ThemedText>
        </Pressable>
      </ThemedView>
    </ScrollView>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <ThemedView style={styles.field}>
      <ThemedText type="defaultSemiBold">{label}</ThemedText>
      {children}
      {error ? <ThemedText style={styles.errorText}>{error}</ThemedText> : null}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 24 },
  form: { gap: 16 },
  field: { gap: 6 },
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