import tkinter as tk

suma = 0.0


def adauga_bani():
    global suma

    suma_adaugata = entry_adaugare_bani.get()
    try:
        valoare = float(suma_adaugata)
        suma += valoare
        entry_adaugare_bani.delete(0, tk.END)
        label_suma.config(text=f"Suma curentă: {suma:.2f} RON", fg="black")
        label_eroare.config(text="")
    except ValueError:
        label_eroare.config(text="Introduceți un număr valid!", fg="red")
        entry_adaugare_bani.delete(0, tk.END)

def extrage_bani():
    global suma 

    suma_extrasa = entry_extras_bani.get()
    try:
        valoare = float(suma_extrasa)
        if valoare > suma:
            label_eroare.config(text="Fonduri insuficiente!", fg="red")
        else:
            suma -= valoare
            entry_extras_bani.delete(0, tk.END)
            label_suma.config(text=f"Suma curentă: {suma:.2f} RON", fg="black")
            label_eroare.config(text="")
    except ValueError:
        label_eroare.config(text="Introduceți un număr valid!", fg="red")
        entry_extras_bani.delete(0, tk.END)

def plateste():
    global suma

    suma_platita = entry_suma_platita.get()
    try:
        valoare = float(suma_platita)
        if valoare > suma:
            label_eroare.config(text="Fonduri insuficiente!", fg="red")
        else:
            if entry_plati.get() != "":
                suma -= valoare
                entry_suma_platita.delete(0, tk.END)
                entry_plati.delete(0, tk.END)  
                label_suma.config(text=f"Suma curentă: {suma:.2f} RON", fg="black")
                label_eroare.config(text="")
                label_ultima_transactie.config(text=f"Ultima tranzacție: {entry_plati.get()} cu valoarea {valoare} RON")
            else :
                label_eroare.config(text="Introduceți un nume pentru plată!", fg="red")
                entry_suma_platita.delete(0, tk.END)
    except ValueError:
        label_eroare.config(text="Introduceți un număr valid!", fg="red")
        entry_suma_platita.delete(0, tk.END)

def deschide_fereastra():
    fereastra_noua = tk.Toplevel(window)
    fereastra_noua.title("Fereastra nouă")
    fereastra_noua.geometry("300x300")

    variable_check = tk.IntVar()

    def transfer_bani():
        global suma
        suma_transferata = entry_bani_transferati.get()
        try:
            valoare = float(suma_transferata)
            if valoare > suma:
                label_eroare.config(text="Fonduri insuficiente!", fg="red")
            else:
                if entry_nou.get() == "":
                    label_eroare.config(text="Introduceți un nume pentru transfer!", fg="red")
                    entry_bani_transferati.delete(0, tk.END)
                else:
                    if entry_iban.get() == "":
                        if variable_check.get() == 1:
                            suma -= valoare
                            entry_bani_transferati.delete(0, tk.END)
                            label_suma.config(text=f"Suma curentă: {suma:.2f} RON", fg="black")
                            label_eroare.config(text="")
                            entry_nou.delete(0, tk.END)
                            label_ultima_transactie.config(text=f"Ultima tranzacție: Transfer între prieteni cu valoarea {valoare} RON")
                        else:
                            label_eroare.config(text="Introduceți un IBAN!", fg="red")
                            entry_bani_transferati.delete(0, tk.END)
                            entry_nou.delete(0, tk.END)
                    else:
                        label_eroare.config(text="")
                        label_ultima_transactie.config(text=f"Ultima tranzacție: Transfer către {entry_nou.get()} cu valoarea {valoare} RON")
                        suma -= valoare
                        entry_bani_transferati.delete(0, tk.END)
                        label_suma.config(text=f"Suma curentă: {suma:.2f} RON", fg="black")
                        label_eroare.config(text="")
                        label_ultima_transactie.config(text=f"Ultima tranzacție: Transfer către {entry_nou.get()} cu valoarea {valoare} RON")
        except ValueError:
            label_eroare.config(text="Introduceți un număr valid!", fg="red")
            entry_bani_transferati.delete(0, tk.END)

    label_nou = tk.Label(fereastra_noua, text="Transfer catre:")
    label_nou.grid(row=0, column=0, padx=10, pady=10)

    entry_nou = tk.Entry(fereastra_noua)
    entry_nou.grid(row=0, column=1, padx=10, pady=10)

    label_suma_transferata = tk.Label(fereastra_noua, text="Suma transferată:")
    label_suma_transferata.grid(row=1, column=0, padx=10, pady=10)

    entry_bani_transferati = tk.Entry(fereastra_noua)
    entry_bani_transferati.grid(row=1, column=1, padx=10, pady=10)

    label_iban = tk.Label(fereastra_noua, text="IBAN:")
    label_iban.grid(row=2, column=0, padx=10, pady=10)

    entry_iban = tk.Entry(fereastra_noua)
    entry_iban.grid(row=2, column=1, padx=10, pady=10)

    button_transfer_bani = tk.Button(fereastra_noua, text="Transferă", command=transfer_bani)
    button_transfer_bani.grid(row=3, column=1, columnspan=2, pady=10, padx=10)

    label_eroare = tk.Label(fereastra_noua, text="")
    label_eroare.grid(row=4, column=0, columnspan=2)

    check_prieten = tk.Checkbutton(fereastra_noua, text="Transfer între prieteni pe aplicatie?", variable=variable_check, onvalue=1, offvalue=0)
    variable_check.set(0)  # Setează valoarea implicită a checkbox-ului la 0 (off)
    check_prieten.grid(row=5, column=0, columnspan=2, padx=10, pady=10)



window = tk.Tk()
window.title("Bank App")
window.geometry("400x400")

label_adaugare_bani = tk.Label(window, text="Adăugare bani:")
label_adaugare_bani.grid(row=1, column=0, padx=10, pady=10)

label_extras_bani = tk.Label(window, text="Extrage bani:")
label_extras_bani.grid(row=2, column=0, padx=10, pady=10)

label_plata = tk.Label(window, text="Plătește catre:")
label_plata.grid(row=3, column=0, padx=10, pady=10)

entry_adaugare_bani = tk.Entry(window)
entry_adaugare_bani.grid(row=1, column=1, padx=10, pady=10)

entry_extras_bani = tk.Entry(window)
entry_extras_bani.grid(row=2, column=1, padx=10, pady=10)

entry_plati = tk.Entry(window)
entry_plati.grid(row=3, column=1, padx=10, pady=10)

entry_suma_platita = tk.Entry(window)
entry_suma_platita.grid(row=4, column=1, padx=10, pady=10)

button_adaugare = tk.Button(window, text="Adaugă", command=adauga_bani)
button_adaugare.grid(row=1, column=2, padx=10, pady=10)

button_extras = tk.Button(window, text="Extrage" ,command=extrage_bani)  
button_extras.grid(row=2, column=2, padx=10, pady=10)

button_plati = tk.Button(window, text="Plătește", command=plateste)
button_plati.grid(row=3, column=2, padx=10, pady=10)

button_transfer = tk.Button(window, text="Transfer nou", command=deschide_fereastra)
button_transfer.grid(row=5, column=1, padx=10, pady=10)

label_suma = tk.Label(window, text="Suma curentă: 0.00 RON")
label_suma.grid(row=0, column=0, columnspan=3, pady=10)

label_eroare = tk.Label(window, text="")
label_eroare.grid(row=6, column=0, columnspan=3)

label_suma_plata = tk.Label(window, text="Suma de:")
label_suma_plata.grid(row=4, column=0, padx=10, pady=10)

label_ultima_transactie = tk.Label(window, text="Ultima tranzacție:")
label_ultima_transactie.grid(row=7, column=0, columnspan=3, pady=10)

window.mainloop()
