from datetime import datetime
import math


class Vehicle:
    def __init__(self, vehicle_number, vehicle_type):
        self.vehicle_number = vehicle_number
        self.vehicle_type = vehicle_type

    def display_details(self):
        print("Vehicle Number:", self.vehicle_number)
        print("Vehicle Type:", self.vehicle_type)

    def calculate_fee(self, hours):
        return hours * 20


class Car(Vehicle):
    def calculate_fee(self, hours):
        return hours * 20


class Bike(Vehicle):
    def calculate_fee(self, hours):
        return hours * 10


class ParkingSlot:
    def __init__(self, slot_id):
        self.slot_id = slot_id
        self.status = "Available"
        self.vehicle = None
        self.ticket = None

    def occupy_slot(self, vehicle):
        if self.status == "Available":
            self.vehicle = vehicle
            self.status = "Occupied"
            return True
        return False

    def free_slot(self):
        self.vehicle = None
        self.ticket = None
        self.status = "Available"

    def display_slot(self):
        print("Slot ID:", self.slot_id)
        print("Status:", self.status)
        if self.status == "Occupied" and self.vehicle is not None:
            print("Vehicle Number:", self.vehicle.vehicle_number)


class ParkingLot:
    def __init__(self, number_of_slots):
        self.slots = []
        for number in range(1, number_of_slots + 1):
            slot = ParkingSlot("P" + str(number))
            self.slots.append(slot)

    def display_all_slots(self):
        for slot in self.slots:
            slot.display_slot()
            print()

    def find_available_slot(self):
        for slot in self.slots:
            if slot.status == "Available":
                return slot
        return None

    def park_vehicle(self, vehicle, available_slot_ids=None, preferred_slot_id=None):
        if preferred_slot_id is not None:
            for slot in self.slots:
                if slot.slot_id == preferred_slot_id and slot.status == "Available":
                    if slot.occupy_slot(vehicle):
                        return slot

        for slot in self.slots:
            is_allowed = (
                available_slot_ids is None or slot.slot_id in available_slot_ids
            )
            if slot.status == "Available" and is_allowed and slot.occupy_slot(vehicle):
                return slot
        return None

    def remove_vehicle(self, slot_id):
        for slot in self.slots:
            if slot.slot_id == slot_id:
                slot.free_slot()
                return True
        return False


class ParkingTicket:
    def __init__(self, vehicle, slot_id):
        self.vehicle = vehicle
        self.slot_id = slot_id
        self.entry_time = datetime.now()
        self.exit_time = None

    def record_exit(self):
        self.exit_time = datetime.now()

    def calculate_duration(self):
        if self.exit_time is None:
            print("Vehicle has not exited yet.")
            return None

        time_difference = self.exit_time - self.entry_time
        duration_in_hours = time_difference.total_seconds() / 3600
        return duration_in_hours


class Payment:
    def calculate_fee(self, vehicle_type, hours):
        if vehicle_type.lower() == "bike":
            rate_per_hour = 10
        else:
            rate_per_hour = 20

        # Charge for each started hour. For example, 2.5 hours is billed as 3.
        billable_hours = math.ceil(hours)
        return billable_hours * rate_per_hour
