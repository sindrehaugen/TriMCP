package launch

import "testing"

func TestUpsertEnv(t *testing.T) {
	base := []string{"FOO=1", "TRIMCP_BACKEND=cpu", "BAR=2"}
	got := UpsertEnv(base, "TRIMCP_BACKEND", "cuda")
	if LookupEnv(got, "TRIMCP_BACKEND") != "cuda" {
		t.Fatalf("backend: %v", got)
	}
	if LookupEnv(got, "FOO") != "1" || LookupEnv(got, "BAR") != "2" {
		t.Fatalf("preserved: %v", got)
	}
	got2 := UpsertEnv([]string{"A=b"}, "TRIMCP_BACKEND", "mps")
	if LookupEnv(got2, "TRIMCP_BACKEND") != "mps" {
		t.Fatal(got2)
	}
}
